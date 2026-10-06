"""Live mode: catch up from the checkpoint once, then write each new source-group message the moment
Telegram pushes it. Every few minutes the newest messages are re-checked (one request) so anything a
dropped connection missed is still written; a message id is never written twice.
"""

import asyncio
import json
import os
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from telethon.errors import BadRequestError

from src.crawler.messages import extract_referenced_group_link, extract_referenced_group_name, normalize_message, output_path
from src.storage.jsonl import append_message_jsonl, load_checkpoint, save_checkpoint

RESYNC_SECONDS = 300
RESYNC_LIMIT = 100
HEARTBEAT_SECONDS = 15
RECENT_KEEP = 5000
STATUS_FILE = "listener.json"


class ListenerClient(Protocol):
    """The async part of TdlibClient the listener needs (tests pass a fake)."""

    disconnected: asyncio.Future

    def on_new_message(self, chat_ids: tuple[int, ...], callback: Callable[[dict[str, Any]], None]) -> None: ...
    def iter_messages_async(self, chat_id: int, limit: int | None = None, min_id: int = 0) -> Any: ...
    async def resolve_group_link_async(self, link: str | None) -> int | None: ...


def _now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


class Router:
    """Writes source messages to their group files, each message id at most once."""

    def __init__(self, client: ListenerClient, raw_dir: Path, crawl_until: int | None, log: Callable[[str], None] = print):
        self.client = client
        self.raw_dir = raw_dir
        self.crawl_until = crawl_until
        self.log = log
        self.floor: dict[int, int] = {}          # every id <= floor is already written
        self.recent: dict[int, set[int]] = {}    # ids above the floor written by this run
        self.saved = 0
        self.last_message_at: float | None = None

    def checkpoint_path(self, source_id: int) -> Path:
        return self.raw_dir / ".state" / f"source_{source_id}.json"

    async def catch_up(self, source_id: int) -> int:
        """Write everything posted since the checkpoint, oldest first; afterwards that is the floor."""
        last = load_checkpoint(self.checkpoint_path(source_id))
        pending: list[dict[str, Any]] = []
        async for message in self.client.iter_messages_async(source_id, min_id=last):
            if int(message.get("id", 0)) <= last:
                continue
            date = message.get("date")
            if self.crawl_until is not None and date is not None and date < self.crawl_until:
                break
            pending.append(message)
        for message in reversed(pending):
            await self._write(source_id, message)
        self.floor[source_id] = load_checkpoint(self.checkpoint_path(source_id))
        self.recent[source_id] = set()
        return len(pending)

    async def save(self, message: dict[str, Any]) -> bool:
        """Write a message unless it is already written; True when it was new."""
        source_id = int(message.get("chat_id", 0))
        message_id = int(message.get("id", 0))
        recent = self.recent.setdefault(source_id, set())
        if message_id <= self.floor.get(source_id, 0) or message_id in recent:
            return False
        await self._write(source_id, message)
        recent.add(message_id)
        return True

    async def resync(self, source_id: int) -> int:
        """Re-check the newest messages (one request) and write any the live stream missed."""
        added = 0
        async for message in self.client.iter_messages_async(source_id, limit=RESYNC_LIMIT):
            added += await self.save({**message, "chat_id": source_id})
        recent = self.recent.get(source_id, set())
        if len(recent) > RECENT_KEEP:
            newest = max(recent)
            self.recent[source_id] = {i for i in recent if i > newest - RECENT_KEEP}
        if added:
            self.log(f"[{_now()}] Re-check found {added} missed message(s)")
        return added

    async def _write(self, source_id: int, message: dict[str, Any]) -> None:
        normalized = normalize_message(message)
        try:
            raw_message = json.loads(normalized.raw_message_json)
        except json.JSONDecodeError:
            raw_message = {}
        group_name = extract_referenced_group_name(normalized.text)
        group_id = await self._resolve(extract_referenced_group_link(raw_message))
        path = output_path(self.raw_dir, group_id, group_name)
        append_message_jsonl(path, normalized)
        checkpoint = self.checkpoint_path(source_id)
        if normalized.message_id > load_checkpoint(checkpoint):
            save_checkpoint(checkpoint, normalized.message_id)
        self.saved += 1
        self.last_message_at = time.time()
        self.log(f"[{_now()}] Saved message {normalized.message_id} -> {path.name}")

    async def _resolve(self, link: str | None) -> int | None:
        try:
            return await self.client.resolve_group_link_async(link)
        except (ValueError, BadRequestError) as error:
            self.log(f"  Cannot resolve group link {link}: {error}")
            return None


class StatusFile:
    """Heartbeat the API reads to show whether the listener is running."""

    def __init__(self, path: Path):
        self.path = path
        self.started_at = time.time()

    def write(self, state: str, router: Router) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "state": state,
            "pid": os.getpid(),
            "started_at": self.started_at,
            "updated_at": time.time(),
            "messages_saved": router.saved,
            "last_message_at": router.last_message_at,
        }
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(self.path)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


async def listen(
    client: ListenerClient,
    source_ids: tuple[int, ...],
    raw_dir: Path,
    crawl_until: int | None,
    resync_seconds: float = RESYNC_SECONDS,
    log: Callable[[str], None] = print,
    stop: asyncio.Event | None = None,
) -> Router:
    """Catch up, then save pushed messages until `stop` is set; raises ConnectionError when Telegram drops us."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    client.on_new_message(source_ids, queue.put_nowait)  # subscribe first: nothing posted during catch-up is lost
    router = Router(client, raw_dir, crawl_until, log)
    status = StatusFile(raw_dir / ".state" / STATUS_FILE)
    status.write("catching_up", router)
    for source_id in source_ids:
        count = await router.catch_up(source_id)
        log(f"[{_now()}] Caught up {source_id}: {count} message(s) since the last run")
    log(f"[{_now()}] Listening for new messages (re-check every {int(resync_seconds)} s); press Ctrl+C to stop.")

    loop = asyncio.get_running_loop()
    next_resync = loop.time() + resync_seconds
    stop = stop or asyncio.Event()
    stopping = asyncio.ensure_future(stop.wait())
    try:
        while not stop.is_set():
            status.write("listening", router)
            getter = asyncio.ensure_future(queue.get())
            timeout = max(0.0, min(HEARTBEAT_SECONDS, next_resync - loop.time()))
            done, _ = await asyncio.wait({getter, client.disconnected, stopping}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if getter in done:
                await router.save(getter.result())
            else:
                getter.cancel()
            if client.disconnected in done:
                raise ConnectionError("lost the connection to Telegram")
            if loop.time() >= next_resync:
                for source_id in source_ids:
                    await router.resync(source_id)
                next_resync = loop.time() + resync_seconds
    finally:
        stopping.cancel()
        status.clear()
    return router
