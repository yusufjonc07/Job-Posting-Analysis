"""Server-sent events: the ingest thread publishes, every connected client gets its own queue."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable

log = logging.getLogger("src.api.events")

PING_SECONDS = 15.0
QUEUE_SIZE = 256


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class Broadcaster:
    """Fans events out to subscriber queues; `publish` is safe to call from any thread."""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queues: set[asyncio.Queue] = set()
        self.closed = False

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def publish(self, event: str, data: dict) -> None:
        self._send(sse(event, data))

    def close(self) -> None:
        """End every stream (server shutdown), so open connections do not block the exit."""
        self.closed = True
        self._send(None)

    def _send(self, message: str | None) -> None:
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._fan_out, message)
        except RuntimeError:  # loop closed between the check and the call (shutdown)
            pass

    def _fan_out(self, message: str | None) -> None:
        for queue in list(self.queues):
            if queue.full():  # a stalled client loses its oldest event rather than blocking everyone
                queue.get_nowait()
            queue.put_nowait(message)

    async def stream(self, hello: Callable[[], dict], ping_seconds: float = PING_SECONDS) -> AsyncIterator[str]:
        """One client's event stream: hello first, then published events and keep-alive pings."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        self.queues.add(queue)
        try:
            yield sse("hello", hello())
            while not self.closed:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=ping_seconds)
                except TimeoutError:
                    message = ": ping\n\n"
                if message is None:
                    break
                yield message
        finally:
            self.queues.discard(queue)
