"""Live Telegram listener, persistent lookup cache, session lock and API supervisor — all without Telegram."""

import asyncio
import dataclasses
import json
import sys
import tempfile
import time
import unittest
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from telethon.errors import UsernameNotOccupiedError

from src import main as crawler
from src.api.telegram import ListenerSupervisor
from src.crawler.listen import STATUS_FILE, Router, known_group_ids, listen
from src.storage.jsonl import load_checkpoint, save_checkpoint
from src.tdlib.cache import LookupCache
from src.tdlib.client import TdlibClient

SOURCE_ID = -1009000000001
LINK = "https://t.me/c/1987654321/42"
LINKED_FILE = "group_-1001987654321.jsonl"
START = int(datetime(2026, 10, 1, tzinfo=UTC).timestamp())


def post(message_id: int, group: str = "Daeso arbayt", link: str | None = LINK) -> dict[str, Any]:
    """A forwarded post in the shape TdlibClient yields (same as the crawler tests)."""
    text = f"Zavodga ishchi kerak, post {message_id}\nGuruh: {group}"
    entities = [{"_": "MessageEntityTextUrl", "offset": text.index(group), "length": len(group), "url": link}] if link else []
    raw = {
        "_": "Message",
        "id": message_id,
        "peer_id": {"_": "PeerChannel", "channel_id": int(str(SOURCE_ID).removeprefix("-100"))},
        "date": datetime.fromtimestamp(START + message_id, UTC).isoformat(sep=" "),
        "message": text,
        "entities": entities,
    }
    return {
        "id": message_id,
        "chat_id": SOURCE_ID,
        "date": START + message_id,
        "raw_message_json": json.dumps(raw, ensure_ascii=False),
        "content": {"@type": "messageText", "text": {"text": text}},
    }


DIRECT_ID = -1001111111111
DIRECT_FILE = f"group_{DIRECT_ID}.jsonl"


def direct_post(message_id: int) -> dict[str, Any]:
    """A message written straight in a directly followed group."""
    text = f"Mokpoda ish bor, post {message_id}"
    raw = {
        "_": "Message",
        "id": message_id,
        "peer_id": {"_": "PeerChannel", "channel_id": int(str(DIRECT_ID).removeprefix("-100"))},
        "date": datetime.fromtimestamp(START + message_id, UTC).isoformat(sep=" "),
        "message": text,
    }
    return {
        "id": message_id,
        "chat_id": DIRECT_ID,
        "date": START + message_id,
        "raw_message_json": json.dumps(raw, ensure_ascii=False),
        "content": {"@type": "messageText", "text": {"text": text}},
    }


class FakeTelegram:
    """Async client double: a message history, pushed events and a connection that can drop."""

    def __init__(self, history: list[dict[str, Any]]):
        self.history = list(history)
        self.callback: Callable[[dict[str, Any]], None] | None = None
        self.disconnected: asyncio.Future = asyncio.get_running_loop().create_future()
        self.requests: list[tuple[int | None, int]] = []
        self.during_history: list[dict[str, Any]] = []   # pushed while the catch-up is reading

    def on_new_message(self, chat_ids: tuple[int, ...], callback: Callable[[dict[str, Any]], None]) -> None:
        self.callback = callback

    def push(self, message: dict[str, Any]) -> None:
        self.history.append(message)
        assert self.callback is not None
        self.callback(message)

    async def iter_messages_async(self, chat_id: int, limit: int | None = None, min_id: int = 0):
        self.requests.append((limit, min_id))
        newest_first = sorted((m for m in self.history if m["chat_id"] == chat_id and m["id"] > min_id), key=lambda m: m["id"], reverse=True)
        for message in self.during_history:
            self.push(message)
        self.during_history = []
        for message in newest_first[:limit]:
            yield message

    async def resolve_group_link_async(self, link: str | None) -> int | None:
        return -1001987654321 if link else None


class ListenerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="listener-test-")))
        self.raw = self.root / "raw"
        self.checkpoint = self.raw / ".state" / f"source_{SOURCE_ID}.json"
        self.logs: list[str] = []

    def stored(self) -> list[int]:
        path = self.raw / LINKED_FILE
        if not path.exists():
            return []
        return [json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines()]

    async def run_listener(self, client: FakeTelegram, script: Callable[[asyncio.Event], Any], resync: float = 3600) -> Router:
        stop = asyncio.Event()
        task = asyncio.create_task(listen(client, (SOURCE_ID,), self.raw, None, resync, self.logs.append, stop))
        await asyncio.sleep(0.05)
        await script(stop)
        stop.set()
        return await asyncio.wait_for(task, 5)

    async def test_catches_up_oldest_first_then_saves_pushed_messages_once(self):
        save_checkpoint(self.checkpoint, 2)
        client = FakeTelegram([post(i) for i in range(1, 6)])
        client.during_history = [post(6)]   # arrives while the catch-up is still reading

        async def script(stop):
            client.push(post(7))
            client.push(post(7))          # Telegram may deliver an update twice
            await asyncio.sleep(0.05)

        router = await self.run_listener(client, script)
        self.assertEqual(self.stored(), [3, 4, 5, 6, 7], "catch-up oldest first, then pushed messages, each once")
        self.assertEqual(load_checkpoint(self.checkpoint), 7)
        self.assertEqual(router.saved, 5)
        self.assertEqual(client.requests[0], (None, 2), "catch-up reads only what is newer than the checkpoint")

    async def test_stale_checkpoint_never_rewrites_stored_messages_but_fills_gaps(self):
        # An interrupted newest-first crawl stored 3, 4 and 6 but left the checkpoint at 2.
        self.raw.mkdir(parents=True)
        with (self.raw / LINKED_FILE).open("w", encoding="utf-8") as target:
            for message_id in (6, 4, 3):
                target.write(json.dumps(json.loads(post(message_id)["raw_message_json"]), ensure_ascii=False) + "\n")
        save_checkpoint(self.checkpoint, 2)
        client = FakeTelegram([post(i) for i in range(1, 8)])

        async def script(stop):
            await asyncio.sleep(0.05)

        router = await self.run_listener(client, script)
        self.assertEqual(self.stored(), [6, 4, 3, 5, 7], "only the gap (5) and the new message (7) are written")
        self.assertEqual(router.saved, 2)
        self.assertEqual(load_checkpoint(self.checkpoint), 7, "the stale checkpoint is repaired")

    async def test_heartbeat_reports_catch_up_progress(self):
        client = FakeTelegram([post(i) for i in range(1, 4)])
        status_path = self.raw / ".state" / STATUS_FILE

        async def script(stop):
            await asyncio.sleep(0.05)
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual((status["state"], status["catch_up_read"], status["messages_saved"]), ("listening", 3, 3))

        await self.run_listener(client, script)

    async def test_recheck_writes_missed_messages_only(self):
        save_checkpoint(self.checkpoint, 3)
        client = FakeTelegram([post(i) for i in range(1, 4)])

        async def script(stop):
            client.push(post(4))
            client.history.append(post(5))   # never pushed: a dropped connection lost it
            await asyncio.sleep(0.4)

        await self.run_listener(client, script, resync=0.2)
        self.assertEqual(self.stored(), [4, 5])
        self.assertIn((100, 0), client.requests, "the re-check asks for the newest messages in one request")

    async def test_heartbeat_while_listening_and_cleared_after(self):
        client = FakeTelegram([])
        status_path = self.raw / ".state" / STATUS_FILE

        async def script(stop):
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "listening")

        await self.run_listener(client, script)
        self.assertFalse(status_path.exists())

    async def test_direct_group_catches_up_from_its_newest_stored_message_then_gets_pushes(self):
        self.raw.mkdir(parents=True)
        with (self.raw / DIRECT_FILE).open("w", encoding="utf-8") as target:
            for message_id in (1, 2, 3):
                target.write(json.dumps(json.loads(direct_post(message_id)["raw_message_json"])) + "\n")
        self.assertIn(DIRECT_ID, known_group_ids(self.raw))
        client = FakeTelegram([direct_post(i) for i in range(1, 6)] + [post(10)])
        save_checkpoint(self.checkpoint, 9)

        async def script(stop):
            client.push(direct_post(6))
            client.push(post(11))
            await asyncio.sleep(0.05)

        stop = asyncio.Event()
        task = asyncio.create_task(listen(client, (SOURCE_ID,), self.raw, None, 3600, self.logs.append, stop, live_ids=(DIRECT_ID,)))
        await asyncio.sleep(0.05)
        await script(stop)
        stop.set()
        await asyncio.wait_for(task, 5)
        direct = [json.loads(line)["id"] for line in (self.raw / DIRECT_FILE).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(direct, [1, 2, 3, 4, 5, 6], "the gap since the newest stored message (4, 5) and the push (6)")
        self.assertEqual(self.stored(), [10, 11], "source posts are still routed by their Guruh link")
        self.assertIn((None, 3), client.requests, "the direct group is read only after its newest stored message")

    async def test_group_not_joined_is_backfilled_to_its_cutoff_then_checked_in_turn(self):
        # No direct history: read back only to `since` (the newest post we had for it), then poll.
        client = FakeTelegram([direct_post(i) for i in range(1, 7)])
        status_path = self.raw / ".state" / STATUS_FILE
        stop = asyncio.Event()
        with mock.patch("src.crawler.listen.MIN_POLL_SPACING", 0.05):
            task = asyncio.create_task(listen(
                client, (SOURCE_ID,), self.raw, None, 3600, self.logs.append, stop,
                polled_ids=(DIRECT_ID,), poll_seconds=0.1, since={DIRECT_ID: START + 4},
            ))
            await asyncio.sleep(0.1)
            client.history.append(direct_post(7))   # never pushed: the account is not a member
            await asyncio.sleep(0.4)
            status = json.loads(status_path.read_text(encoding="utf-8"))
            stop.set()
            await asyncio.wait_for(task, 5)
        direct = [json.loads(line)["id"] for line in (self.raw / DIRECT_FILE).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(direct, [5, 6, 7], "posts after the cutoff, then the polled one; nothing older")
        self.assertEqual(status["groups"], {"live": 0, "polled": 1, "skipped": 0})
        polls = [request for request in client.requests if request == (None, 6)]
        self.assertTrue(polls, "a check asks only for messages newer than the newest stored one")

    async def test_an_inaccessible_direct_group_is_skipped_not_fatal(self):
        client = FakeTelegram([post(1)])
        original = client.iter_messages_async

        def iter_messages(chat_id, limit=None, min_id=0):
            if chat_id == DIRECT_ID:
                raise ValueError("Could not find the input entity")
            return original(chat_id, limit, min_id)

        client.iter_messages_async = iter_messages

        stop = asyncio.Event()
        task = asyncio.create_task(listen(client, (SOURCE_ID,), self.raw, None, 3600, self.logs.append, stop, polled_ids=(DIRECT_ID,)))
        await asyncio.sleep(0.05)
        client.push(post(2))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, 5)
        self.assertEqual(self.stored(), [1, 2])
        self.assertTrue(any("Skipping group" in line for line in self.logs))

    async def test_lost_connection_ends_the_listener_with_an_error(self):
        client = FakeTelegram([])
        task = asyncio.create_task(listen(client, (SOURCE_ID,), self.raw, None, 3600, self.logs.append))
        await asyncio.sleep(0.05)
        client.disconnected.set_result(None)
        with self.assertRaises(ConnectionError):
            await asyncio.wait_for(task, 5)


class KnownGroupsTests(unittest.TestCase):
    def test_ids_come_from_file_names_and_the_groups_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory)
            for name in ("group_-1001111111111.jsonl", "group_2222222222.jsonl", "group_unmatched_Some_group.jsonl"):
                (raw / name).write_text("", encoding="utf-8")
            groups_csv = raw / "groups.csv"
            groups_csv.write_text("group_id,group_title,message_count,last_msg_date,province,city\n-1003333333333,X,1,,,\n", encoding="utf-8")
            self.assertEqual(known_group_ids(raw, groups_csv), (-1003333333333, -1002222222222, -1001111111111))


class LookupCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_link_and_title_is_requested_from_telegram_once_across_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telegram_lookups.json"
            telethon = mock.MagicMock()
            telethon.get_entity = mock.AsyncMock(side_effect=lambda target: mock.Mock(id=1234, title=f"Group {target}"))
            with mock.patch("src.tdlib.client.TelegramClient", return_value=telethon):
                first = TdlibClient(1, "hash", "+1", Path(directory) / "tdlib", cache=LookupCache(path))
                self.assertEqual(await first.resolve_group_link_async("https://t.me/somegroup"), 1234)
                self.assertEqual(await first.resolve_group_link_async("https://t.me/somegroup"), 1234)
                self.assertEqual(await first.get_group_title_async(SOURCE_ID), f"Group {SOURCE_ID}")
                self.assertEqual(telethon.get_entity.await_count, 2)

                second = TdlibClient(1, "hash", "+1", Path(directory) / "tdlib", cache=LookupCache(path))  # a new run
                self.assertEqual(await second.resolve_group_link_async("https://t.me/somegroup"), 1234)
                self.assertEqual(await second.get_group_title_async(SOURCE_ID), f"Group {SOURCE_ID}")
                self.assertEqual(telethon.get_entity.await_count, 2, "a cached lookup went to Telegram again")

    async def test_a_link_telegram_rejected_is_not_requested_again(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telegram_lookups.json"
            telethon = mock.MagicMock()
            telethon.get_entity = mock.AsyncMock(side_effect=UsernameNotOccupiedError(request=None))
            with mock.patch("src.tdlib.client.TelegramClient", return_value=telethon):
                client = TdlibClient(1, "hash", "+1", Path(directory) / "tdlib", cache=LookupCache(path))
                with self.assertRaises(UsernameNotOccupiedError):
                    await client.resolve_group_link_async("https://t.me/gone_group")
                again = TdlibClient(1, "hash", "+1", Path(directory) / "tdlib", cache=LookupCache(path))
                self.assertIsNone(await again.resolve_group_link_async("https://t.me/gone_group"))
                self.assertEqual(telethon.get_entity.await_count, 1)


class CanReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_known_to_the_session_needs_no_request_else_the_public_username_is_resolved_once(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = LookupCache(Path(directory) / "telegram_lookups.json")
            cache.set_link("https://t.me/public_jobs", 5555555555)
            telethon = mock.MagicMock()
            known = {-1004444444444}
            telethon.get_input_entity = mock.AsyncMock(side_effect=lambda chat: chat if chat in known else (_ for _ in ()).throw(ValueError("unknown")))
            telethon.get_entity = mock.AsyncMock(return_value=mock.Mock(id=5555555555))
            with mock.patch("src.tdlib.client.TelegramClient", return_value=telethon):
                client = TdlibClient(1, "hash", "+1", Path(directory) / "tdlib", cache=cache)
                self.assertTrue(await client.can_read_async(-1004444444444))
                self.assertEqual(telethon.get_entity.await_count, 0, "a chat in the session needs no request")
                self.assertTrue(await client.can_read_async(-1005555555555))
                telethon.get_entity.assert_awaited_once_with("public_jobs")
                self.assertFalse(await client.can_read_async(-1006666666666), "private and unknown: cannot be read")


class SessionLockTests(unittest.TestCase):
    def test_a_second_crawler_or_listener_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = dataclasses.replace(crawler.settings, tdlib_database_dir=Path(directory) / "tdlib", raw_data_dir=Path(directory) / "raw")
            with mock.patch.object(crawler, "settings", settings):
                held = crawler.acquire_session_lock()
                self.assertIsNotNone(held)
                try:
                    with mock.patch.object(crawler, "TdlibClient") as factory, self.assertRaises(SystemExit) as exit_info:
                        crawler.main(["--listen"])
                    self.assertEqual(exit_info.exception.code, crawler.EXIT_LOCKED)
                    factory.assert_not_called()
                finally:
                    held.close()
                self.assertIsNotNone(crawler.acquire_session_lock(), "the lock must be free again")

    def test_listen_and_every_are_exclusive_and_resync_has_a_floor(self):
        with mock.patch("sys.stderr"):
            for argv in (["--listen", "--every", "60"], ["--listen", "--resync", "10"]):
                with self.subTest(argv=argv), self.assertRaises(SystemExit):
                    crawler.parse_args(argv)
        self.assertTrue(crawler.parse_args(["--listen"]).listen)
        self.assertEqual(crawler.parse_args(["--listen", "--resync", "120"]).resync, 120)


class SupervisorTests(unittest.IsolatedAsyncioTestCase):
    async def test_not_logged_in_stops_restarting(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [sys.executable, "-c", f"import sys; print('need login'); sys.exit({crawler.EXIT_NOT_LOGGED_IN})"]
            supervisor = ListenerSupervisor(Path(directory), enabled=True, command=command)
            supervisor.start()
            await asyncio.wait_for(supervisor._task, 10)
            self.assertEqual(supervisor.status()["state"], "login_required")
            self.assertEqual(supervisor.restarts, 0)

    async def test_crash_is_restarted_and_stop_ends_the_process(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "runs"
            script = f"import pathlib, sys, time; p = pathlib.Path({str(marker)!r}); n = int(p.read_text()) if p.exists() else 0; p.write_text(str(n + 1)); sys.exit(1) if n == 0 else time.sleep(60)"
            supervisor = ListenerSupervisor(Path(directory), enabled=True, command=[sys.executable, "-c", script])
            with mock.patch("src.api.telegram.RESTART_SECONDS", (0.1,)):
                supervisor.start()
                deadline = time.monotonic() + 10
                while not (marker.exists() and marker.read_text() == "2"):
                    self.assertLess(time.monotonic(), deadline, "the crashed listener was not restarted")
                    await asyncio.sleep(0.05)
                self.assertEqual(supervisor.restarts, 1)
                await supervisor.stop()
            self.assertIsNotNone(supervisor.process.returncode)

    async def test_heartbeat_of_a_listener_started_by_hand_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory)
            (raw / ".state").mkdir()
            (raw / ".state" / STATUS_FILE).write_text(json.dumps({"state": "listening", "updated_at": time.time(), "messages_saved": 3, "last_message_at": time.time()}))
            status = ListenerSupervisor(raw, enabled=False).status()
            self.assertEqual((status["state"], status["managed"], status["messages_saved"]), ("listening", False, 3))


if __name__ == "__main__":
    unittest.main()
