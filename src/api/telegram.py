"""Runs the Telegram listener (`python -m src.main --listen`) next to the API and reports its state.

The listener is a separate process because a Telethon session can only be used by one process, and a
Telegram reconnect or crash should never take the web server down. It writes new posts to data/raw,
which the store picks up within a fraction of a second.
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from config.settings import PROJECT_ROOT
from src.crawler.listen import HEARTBEAT_SECONDS, STATUS_FILE
from src.main import EXIT_LOCKED, EXIT_NOT_LOGGED_IN

log = logging.getLogger("src.api.telegram")

RESTART_SECONDS = (5, 10, 30, 60)
STOP_SECONDS = 10.0
EXTERNAL_CHECK_SECONDS = 60.0


def iso(timestamp: float | None) -> str | None:
    return datetime.fromtimestamp(timestamp, UTC).isoformat() if timestamp else None


def read_status(raw_dir: Path) -> dict | None:
    """The listener's heartbeat file, or None when it is missing or stale."""
    try:
        status = json.loads((raw_dir / ".state" / STATUS_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if time.time() - float(status.get("updated_at", 0)) > 3 * HEARTBEAT_SECONDS:
        return None
    return status


class ListenerSupervisor:
    """Starts the listener, restarts it with backoff when it exits, stops it with the server."""

    def __init__(self, raw_dir: Path, enabled: bool, command: list[str] | None = None):
        self.raw_dir = raw_dir
        self.enabled = enabled
        self.command = command or [sys.executable, "-m", "src.main", "--listen"]
        self.state = "starting" if enabled else "disabled"
        self.restarts = 0
        self.process: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task | None = None
        self._stopping = False

    def start(self) -> None:
        if self.enabled:
            self._task = asyncio.create_task(self._supervise())

    async def stop(self) -> None:
        self._stopping = True
        process = self.process
        if process and process.returncode is None:
            process.send_signal(signal.SIGINT)
            try:
                await asyncio.wait_for(process.wait(), STOP_SECONDS)
            except TimeoutError:
                process.kill()
                await process.wait()
        if self._task:
            self._task.cancel()

    def status(self) -> dict:
        heartbeat = read_status(self.raw_dir)
        state = self.state
        if heartbeat and state in {"starting", "running", "external", "disabled"}:
            state = heartbeat["state"]  # catching_up / listening, also for a listener started by hand
        elif state == "running":
            state = "connecting"
        return {
            "state": state,
            "managed": self.enabled,
            "restarts": self.restarts,
            "messages_saved": int(heartbeat.get("messages_saved", 0)) if heartbeat else 0,
            "catch_up_read": int(heartbeat.get("catch_up_read", 0)) if heartbeat else 0,
            "groups": heartbeat.get("groups") if heartbeat else None,
            "last_message_at": iso(heartbeat.get("last_message_at")) if heartbeat else None,
        }

    async def _supervise(self) -> None:
        attempt = 0
        while not self._stopping:
            code = await self._run_once()
            if self._stopping:
                return
            if code == EXIT_NOT_LOGGED_IN:
                self.state = "login_required"
                log.error("Telegram session is not logged in: run `python -m src.main` once in a terminal, then restart the server")
                return
            if code == EXIT_LOCKED:
                self.state = "external"  # a listener or crawler started by hand holds the session
                log.info("another listener/crawler is using the Telegram session; checking again in %d s", EXTERNAL_CHECK_SECONDS)
                await asyncio.sleep(EXTERNAL_CHECK_SECONDS)
                continue
            delay = RESTART_SECONDS[min(attempt, len(RESTART_SECONDS) - 1)]
            attempt += 1
            self.restarts += 1
            self.state = "restarting"
            log.warning("Telegram listener exited with code %s; restarting in %d s", code, delay)
            await asyncio.sleep(delay)

    async def _run_once(self) -> int:
        self.state = "running"
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=PROJECT_ROOT,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        log.info("Telegram listener started (pid %d)", self.process.pid)
        assert self.process.stdout is not None
        async for line in self.process.stdout:
            text = line.decode("utf-8", "replace").rstrip()
            if text:
                log.info("[telegram] %s", text)
        return await self.process.wait()
