"""Live mode: keep data/raw current for the source group and every group we have an id for.

- Source group (Ish e'lonlari): catch up from the checkpoint, then Telegram pushes each new post; posts are
  routed to the group named in them (group_<id>.jsonl / group_unmatched_*.jsonl), as the crawler does.
- Groups (every id in data/raw file names and telegram_groups.csv): their own messages go to
  group_-100<id>.jsonl. Each first fills the gap since its newest stored message (or, without direct
  history, since the newest post we have for it). Then:
    * joined groups: Telegram pushes new messages (instant);
    * groups the account has not joined: Telegram never pushes those, so they are checked in turn, each
      about every `poll_seconds` with one request that returns only messages newer than the last stored.
- Every few minutes the newest messages of pushed chats are re-checked (one request each) in case a
  dropped connection missed something.

A message id is never written twice: the ids already stored in the raw files are read first, so even a
stale checkpoint (e.g. from an interrupted newest-first crawl) cannot cause re-writes.
"""

import asyncio
import csv
import json
import os
import re
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from telethon.errors import BadRequestError, RPCError

from src.crawler.messages import extract_referenced_group_link, extract_referenced_group_name, normalize_message, output_path
from src.storage.jsonl import append_message_jsonl, load_checkpoint, save_checkpoint
from src.utils.locations import group_id_from_source

RESYNC_SECONDS = 300
RESYNC_LIMIT = 100
POLL_SECONDS = 120
MIN_POLL_SPACING = 1.0         # never more than one check per second across all polled groups
BACKFILL_DAYS = 30             # a group without direct history is read back at most this far
HEARTBEAT_SECONDS = 15
STATUS_FILE = "listener.json"
PROGRESS_EVERY = 500
# The start of a raw line as Telethon's to_dict writes it: message id, the chat it came from, its date.
LINE_START = re.compile(rb'^\{"_": "Message\w*", "id": (\d+), "peer_id": \{"_": "PeerChannel", "channel_id": (\d+)\}(?:, "date": "([^"]+)")?')


class ListenerClient(Protocol):
    """The async part of TdlibClient the listener needs (tests pass a fake)."""

    disconnected: asyncio.Future

    def on_new_message(self, chat_ids: tuple[int, ...], callback: Callable[[dict[str, Any]], None]) -> None: ...
    def iter_messages_async(self, chat_id: int, limit: int | None = None, min_id: int = 0) -> Any: ...
    async def resolve_group_link_async(self, link: str | None) -> int | None: ...


def _now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def known_group_ids(raw_dir: Path, groups_csv: Path | None = None) -> tuple[int, ...]:
    """Every group id we have: from group_<id>.jsonl file names and telegram_groups.csv."""
    ids = {group_id_from_source(path.name) for path in raw_dir.glob("group_*.jsonl")}
    if groups_csv is not None and groups_csv.is_file():
        with groups_csv.open(encoding="utf-8") as source:
            ids |= {int(row["group_id"]) for row in csv.DictReader(source) if row.get("group_id")}
    return tuple(sorted(i for i in ids if i is not None))


def stored_ids(raw_dir: Path, chat_id: int) -> set[int]:
    """Ids of the chat's own messages already in the raw files (a fast scan of each line's start)."""
    channel = str(chat_id).removeprefix("-100").encode()
    ids: set[int] = set()
    for path in raw_dir.glob("group_*.jsonl"):
        with path.open("rb") as source:
            for line in source:
                match = LINE_START.match(line)
                if match and match.group(2) == channel:
                    ids.add(int(match.group(1)))
    return ids


def newest_post_dates(raw_dir: Path) -> dict[int, float]:
    """Per group id: the date of the newest post we have for it (its own or forwarded), as epoch seconds."""
    newest: dict[int, str] = defaultdict(str)
    for path in raw_dir.glob("group_*.jsonl"):
        group_id = group_id_from_source(path.name)
        if group_id is None:
            continue
        with path.open("rb") as source:
            for line in source:
                match = LINE_START.match(line)
                if match and match.group(3):
                    newest[group_id] = max(newest[group_id], match.group(3).decode())
    dates = {}
    for group_id, value in newest.items():
        try:
            dates[group_id] = datetime.fromisoformat(value).timestamp()
        except ValueError:
            continue
    return dates


class Router:
    """Writes messages to their raw files, each message id at most once."""

    def __init__(
        self,
        client: ListenerClient,
        raw_dir: Path,
        crawl_until: int | None,
        log: Callable[[str], None] = print,
        group_ids: tuple[int, ...] = (),
    ):
        self.client = client
        self.raw_dir = raw_dir
        self.groups = set(group_ids)
        self.crawl_until = crawl_until
        self.log = log
        self.written: dict[int, set[int]] = {}   # ids stored in the raw files, per chat
        self.floor: dict[int, int] = {}          # older ids are never written by the listener
        self.saved = 0
        self.read = 0                            # messages read while catching up
        self.last_message_at: float | None = None
        self.counts = {"live": 0, "polled": 0, "skipped": 0}

    def checkpoint_path(self, source_id: int) -> Path:
        return self.raw_dir / ".state" / f"source_{source_id}.json"

    def _count_read(self) -> None:
        self.read += 1
        if self.read % PROGRESS_EVERY == 0:
            self.log(f"[{_now()}] Catching up: {self.read:,} messages read")

    async def catch_up(self, source_id: int) -> int:
        """Source group: write what was posted since the checkpoint and is not stored yet, oldest first."""
        self.written[source_id] = await asyncio.to_thread(stored_ids, self.raw_dir, source_id)
        last = load_checkpoint(self.checkpoint_path(source_id))
        self.floor[source_id] = last
        pending: list[dict[str, Any]] = []
        async for message in self.client.iter_messages_async(source_id, min_id=last):
            self._count_read()
            message_id = int(message.get("id", 0))
            if message_id <= last or message_id in self.written[source_id]:
                continue
            date = message.get("date")
            if self.crawl_until is not None and date is not None and date < self.crawl_until:
                break
            pending.append(message)
        for message in reversed(pending):
            await self.save({**message, "chat_id": source_id})
        newest = max(self.written[source_id], default=0)
        if newest > load_checkpoint(self.checkpoint_path(source_id)):
            save_checkpoint(self.checkpoint_path(source_id), newest)  # repairs a stale checkpoint
        return len(pending)

    async def catch_up_group(self, group_id: int, since: float | None) -> int:
        """A group: write its messages newer than its newest stored one, or, without direct history,
        those posted after `since`; oldest first."""
        self.written[group_id] = await asyncio.to_thread(stored_ids, self.raw_dir, group_id)
        newest = max(self.written[group_id], default=0)
        self.floor[group_id] = newest
        pending: list[dict[str, Any]] = []
        async for message in self.client.iter_messages_async(group_id, min_id=newest):
            self._count_read()
            date = message.get("date")
            if newest == 0 and since is not None and date is not None and date <= since:
                self.floor[group_id] = int(message.get("id", 0))  # older messages stay unread
                break
            pending.append(message)
        for message in reversed(pending):
            await self.save({**message, "chat_id": group_id})
        return len(pending)

    async def poll(self, group_id: int) -> int:
        """One request: write the group's messages newer than the newest one we have."""
        newest = max(self.floor.get(group_id, 0), max(self.written.get(group_id, ()), default=0))
        pending = [message async for message in self.client.iter_messages_async(group_id, min_id=newest)]
        added = 0
        for message in reversed(pending):
            added += await self.save({**message, "chat_id": group_id})
        return added

    async def save(self, message: dict[str, Any]) -> bool:
        """Write a message unless it is already stored; True when it was new."""
        chat_id = int(message.get("chat_id", 0))
        message_id = int(message.get("id", 0))
        written = self.written.setdefault(chat_id, set())
        if message_id in written or message_id <= self.floor.get(chat_id, 0):
            return False
        await self._write(chat_id, message)
        written.add(message_id)
        return True

    async def resync(self, chat_id: int) -> int:
        """Re-check the newest messages (one request) and write any the live stream missed."""
        added = 0
        async for message in self.client.iter_messages_async(chat_id, limit=RESYNC_LIMIT):
            added += await self.save({**message, "chat_id": chat_id})
        if added:
            self.log(f"[{_now()}] Re-check of {chat_id} found {added} missed message(s)")
        return added

    async def _write(self, chat_id: int, message: dict[str, Any]) -> None:
        normalized = normalize_message(message)
        if chat_id in self.groups:
            path = self.raw_dir / f"group_{chat_id}.jsonl"
        else:
            try:
                raw_message = json.loads(normalized.raw_message_json)
            except json.JSONDecodeError:
                raw_message = {}
            group_name = extract_referenced_group_name(normalized.text)
            group_id = await self._resolve(extract_referenced_group_link(raw_message))
            path = output_path(self.raw_dir, group_id, group_name)
        append_message_jsonl(path, normalized)
        if chat_id not in self.groups:
            checkpoint = self.checkpoint_path(chat_id)
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
            "catch_up_read": router.read,
            "last_message_at": router.last_message_at,
            "groups": router.counts,
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
    live_ids: tuple[int, ...] = (),
    polled_ids: tuple[int, ...] = (),
    poll_seconds: float = POLL_SECONDS,
    since: dict[int, float] | None = None,
    skipped: int = 0,
) -> Router:
    """Catch up, then save new messages until `stop` is set; raises ConnectionError when Telegram drops us.

    live_ids: groups the account has joined (Telegram pushes their messages);
    polled_ids: readable groups it has not joined (checked in turn, each about every poll_seconds).
    """
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    pushed = tuple(source_ids) + tuple(live_ids)
    client.on_new_message(pushed, queue.put_nowait)  # subscribe first: nothing posted during catch-up is lost
    router = Router(client, raw_dir, crawl_until, log, tuple(live_ids) + tuple(polled_ids))
    status = StatusFile(raw_dir / ".state" / STATUS_FILE)
    state = "catching_up"
    since = since or {}

    async def heartbeat() -> None:
        # Its own task, so the status stays fresh during a long catch-up or a Telegram flood wait.
        while True:
            status.write(state, router)
            await asyncio.sleep(HEARTBEAT_SECONDS)

    async def catch_up_groups(group_ids: tuple[int, ...]) -> tuple[int, ...]:
        readable, total = [], 0
        for group_id in group_ids:
            try:
                count = await router.catch_up_group(group_id, since.get(group_id))
            except (ValueError, RPCError) as error:  # private, left, or unknown to Telegram
                log(f"[{_now()}] Skipping group {group_id}: {error}")
                router.counts["skipped"] += 1
                continue
            readable.append(group_id)
            total += count
            if count:
                log(f"[{_now()}] Caught up group {group_id}: {count} new message(s)")
        log(f"[{_now()}] Caught up {len(readable)} group(s): {total:,} new message(s)")
        return tuple(readable)

    async def poller(group_ids: tuple[int, ...]) -> None:
        # Telegram does not push messages of groups the account has not joined: ask, one group at a time.
        if not group_ids:
            return
        spacing = max(MIN_POLL_SPACING, poll_seconds / len(group_ids))
        while True:
            for group_id in group_ids:
                try:
                    await router.poll(group_id)
                except (ValueError, RPCError) as error:
                    log(f"[{_now()}] Check of group {group_id} failed, trying again next round: {error}")
                except Exception as error:  # never let one group stop the others
                    log(f"[{_now()}] Check of group {group_id} failed unexpectedly: {error!r}")
                await asyncio.sleep(spacing)

    beating = asyncio.create_task(heartbeat())
    polling: asyncio.Task | None = None
    stop = stop or asyncio.Event()
    stopping = asyncio.ensure_future(stop.wait())
    try:
        router.counts["skipped"] = skipped
        for source_id in source_ids:
            count = await router.catch_up(source_id)
            log(f"[{_now()}] Caught up {source_id}: {count} new message(s) since the last run")
        live = await catch_up_groups(tuple(live_ids))
        polled = await catch_up_groups(tuple(polled_ids))
        router.counts.update(live=len(live), polled=len(polled))
        resynced = tuple(source_ids) + live
        polling = asyncio.create_task(poller(polled))
        state = "listening"
        status.write(state, router)
        log(
            f"[{_now()}] Listening: {len(live)} joined group(s) pushed live, {len(polled)} checked about every "
            f"{int(poll_seconds)} s, {router.counts['skipped']} skipped. Press Ctrl+C to stop."
        )

        loop = asyncio.get_running_loop()
        next_resync = loop.time() + resync_seconds
        while not stop.is_set():
            getter = asyncio.ensure_future(queue.get())
            timeout = max(0.0, next_resync - loop.time())
            done, _ = await asyncio.wait({getter, client.disconnected, stopping}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if getter in done:
                if await router.save(getter.result()):
                    status.write(state, router)
            else:
                getter.cancel()
            if client.disconnected in done:
                raise ConnectionError("lost the connection to Telegram")
            if loop.time() >= next_resync:
                for chat_id in resynced:
                    try:
                        await router.resync(chat_id)
                    except (ValueError, RPCError) as error:
                        log(f"[{_now()}] Re-check of {chat_id} failed, trying again next time: {error}")
                next_resync = loop.time() + resync_seconds
    finally:
        beating.cancel()
        if polling:
            polling.cancel()
        stopping.cancel()
        status.clear()
    return router
