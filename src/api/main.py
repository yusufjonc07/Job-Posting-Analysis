"""FastAPI app for the live dashboard: `uvicorn src.api.main:app --port 8000` from the repo root.

The store loads in a background thread so the server answers at once; stats endpoints return 503
with the loading progress until it is ready. The same thread then polls data/raw for new lines.
"""

import asyncio
import logging
import signal
import threading
from collections import OrderedDict
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from src.api import stats
from src.api.config import ApiConfig, load_config
from src.api.events import Broadcaster
from src.api.store import PROVINCE_IDS, Snapshot, Store
from src.api.telegram import ListenerSupervisor

log = logging.getLogger("src.api")

CACHE_SIZE = 256
SHUTDOWN_SECONDS = 30.0


class StoreLoading(Exception):
    def __init__(self, progress: float):
        self.progress = progress


class StatsCache:
    """Memoizes responses by (endpoint, arguments, store version, minute)."""

    def __init__(self, size: int = CACHE_SIZE):
        self.size = size
        self.items: OrderedDict[tuple, dict] = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key: tuple, compute: Callable[[], dict]) -> dict:
        with self.lock:
            if key in self.items:
                self.items.move_to_end(key)
                return self.items[key]
        value = compute()
        with self.lock:
            self.items[key] = value
            while len(self.items) > self.size:
                self.items.popitem(last=False)
        return value


def setup_logging() -> None:
    logger = logging.getLogger("src.api")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


def progress_logger() -> Callable[[dict], None]:
    """Log loading progress in 10% steps (status events arrive about once a second)."""
    last_step = -1

    def report(health: dict) -> None:
        nonlocal last_step
        step = int(health["progress"] * 10)
        if health["status"] == "loading" and step > last_step:
            last_step = step
            log.info("loading data: %d%%", step * 10)

    return report


def chain_exit_signals(on_exit: Callable[[], None]) -> None:
    """Run `on_exit` before the server's own SIGINT/SIGTERM handler (uvicorn installs it before the app
    loads), so open event streams end and a graceful shutdown does not wait on them forever."""
    for number in (signal.SIGINT, signal.SIGTERM):
        previous = signal.getsignal(number)
        if not callable(previous):
            continue

        def handler(signum, frame, previous=previous):
            on_exit()
            previous(signum, frame)

        try:
            signal.signal(number, handler)
        except ValueError:  # not the main thread (e.g. TestClient); nothing to chain
            return


def create_app(config: ApiConfig | None = None, now: Callable[[], datetime] = stats.utc_now) -> FastAPI:
    """Build the app; tests pass their own config (temp raw/cache dirs) and clock."""
    setup_logging()
    config = config or load_config()
    broadcaster = Broadcaster()
    cache = StatsCache()
    log_progress = progress_logger()
    listener = ListenerSupervisor(config.raw_dir, enabled=config.telegram_listener)

    def full_health(health: dict) -> dict:
        return {**health, "listener": listener.status()}

    def on_status(health: dict) -> None:
        log_progress(health)
        broadcaster.publish("status", full_health(health))

    def on_update(update: dict) -> None:
        log.info("+%d posts (+%d new ads), version %d", update["added_posts"], update["added_ads"], update["version"])
        broadcaster.publish("update", update)

    store = Store(config, on_status=on_status, on_update=on_update)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        broadcaster.bind(asyncio.get_running_loop())
        chain_exit_signals(broadcaster.close)
        stop = threading.Event()
        thread = threading.Thread(target=store.run, args=(stop,), name="ingest", daemon=True)
        log.info("reading %s (cache %s)", config.raw_dir, config.cache_dir)
        thread.start()
        listener.start()
        if not config.telegram_listener:
            log.info("Telegram listener off (API_TELEGRAM_LISTENER=0): new posts appear when a crawler writes them")
        try:
            yield
        finally:
            broadcaster.close()
            await listener.stop()
            stop.set()
            await asyncio.to_thread(thread.join, SHUTDOWN_SECONDS)

    app = FastAPI(title="Job ads live dashboard", lifespan=lifespan)
    app.state.store = store
    app.state.broadcaster = broadcaster
    app.state.listener = listener
    app.add_middleware(CORSMiddleware, allow_origins=list(config.cors_origins), allow_methods=["GET"], allow_headers=["*"])

    @app.exception_handler(StoreLoading)
    async def loading_response(request: Request, error: StoreLoading) -> JSONResponse:
        return JSONResponse({"status": "loading", "progress": round(error.progress, 4)}, status_code=503)

    def snapshot() -> Snapshot:
        if store.status != "ready":
            raise StoreLoading(store.progress)
        return store.snapshot

    def filters(
        days: Annotated[int | None, Query(ge=1)] = None,
        source: Literal["all", "direct", "forwarded"] = "all",
        basis: Literal["all", "post"] = "all",
    ) -> stats.Filters:
        return stats.Filters(days=days, source=source, basis=basis)

    def province_id(province: str) -> str:
        if province not in PROVINCE_IDS:
            raise HTTPException(status_code=404, detail="Unknown region")
        return province

    Ready = Annotated[Snapshot, Depends(snapshot)]
    Filtered = Annotated[stats.Filters, Depends(filters)]

    def cached(name: str, current: Snapshot, compute: Callable[[datetime], dict], *args) -> dict:
        moment = now()
        key = (name, current.version, int(moment.timestamp() // 60), *args)
        return cache.get(key, lambda: compute(moment))

    @app.get("/api/health")
    def health() -> dict:
        return full_health(store.health())

    @app.get("/api/meta")
    def meta(current: Ready) -> dict:
        return cache.get(("meta", current.version), lambda: stats.meta(current))

    def stats_route(name: str, function: Callable) -> None:
        def endpoint(current: Ready, chosen: Filtered) -> dict:
            return cached(name, current, lambda moment: function(current, chosen, moment), chosen)

        app.add_api_route(f"/api/{name}", endpoint, methods=["GET"], name=name)

    for name, function in stats.ENDPOINTS.items():
        stats_route(name, function)

    @app.get("/api/regions/{province}")
    def region(province: Annotated[str, Depends(province_id)], current: Ready, chosen: Filtered) -> dict:
        return cached("region", current, lambda moment: stats.region(current, chosen, moment, province), chosen, province)

    @app.get("/api/feed")
    def feed(
        current: Ready,
        chosen: Filtered,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        province: str | None = None,
    ) -> dict:
        if province is not None:
            province_id(province)
        return cached("feed", current, lambda moment: stats.feed(current, chosen, moment, limit, province),
                      chosen, limit, province)

    @app.get("/api/events")
    async def events() -> StreamingResponse:
        hello = lambda: {"version": store.snapshot.version, "status": store.status}  # noqa: E731
        return StreamingResponse(
            broadcaster.stream(hello),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    mount_frontend(app, config.frontend_dist)
    return app


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve frontend/dist (when built) with an index.html fallback for client-side routes."""
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        index = root / "index.html"
        if not index.is_file():
            return JSONResponse({
                "detail": "Frontend not built. API is at /api/health; run `cd frontend && npm run build`, "
                          "or use the Vite dev server (npm run dev, http://localhost:5173).",
            }, status_code=404)
        target = (root / path).resolve()
        if path and target.is_file() and target.is_relative_to(root):
            return FileResponse(target)
        return FileResponse(index)


app = create_app()
