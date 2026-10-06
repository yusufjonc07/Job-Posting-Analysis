"""Crawler checkpoint and --every loop tests against a fake Telegram client (no network)."""

import contextlib
import dataclasses
import io
import json
import re
import sys
import tempfile
import unittest
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from telethon.errors import UsernameInvalidError

from src import main as crawler
from src.storage.jsonl import load_checkpoint, save_checkpoint

SOURCE_ID = -1009000000001
SOURCE_CHANNEL = 9000000001
DESTINATION_LINK = "https://t.me/c/1987654321/42"
DESTINATION_FILE = "group_-1001987654321.jsonl"
START = int(datetime(2026, 10, 1, tzinfo=UTC).timestamp())


def source_message(message_id: int, group: str | None = "Daeso arbayt", link: str | None = DESTINATION_LINK) -> dict[str, Any]:
    """Build a forwarded post in the shape TdlibClient.iter_messages yields."""
    text = f"Zavodga ishchi kerak, post {message_id}"
    entities: list[dict[str, Any]] = []
    if group is not None:
        text += f"\nGuruh: {group}"
        if link is not None:
            entities.append({"_": "MessageEntityTextUrl", "offset": text.index(group), "length": len(group), "url": link})
    date = START + message_id * 60
    raw = {
        "_": "Message",
        "id": message_id,
        "peer_id": {"_": "PeerChannel", "channel_id": SOURCE_CHANNEL},
        "date": datetime.fromtimestamp(date, UTC).isoformat(sep=" "),
        "message": text,
        "entities": entities,
    }
    return {
        "id": message_id,
        "chat_id": SOURCE_ID,
        "date": date,
        "raw_message_json": json.dumps(raw, ensure_ascii=False),
        "content": {"@type": "messageText", "text": {"text": text}},
    }


def messages(first: int, last: int, **kwargs: Any) -> list[dict[str, Any]]:
    """Build source messages with ids first..last inclusive."""
    return [source_message(message_id, **kwargs) for message_id in range(first, last + 1)]


class FakeClient:
    """In-memory TdlibClient: serves one source group newest first, excluding ids <= min_id like Telethon."""

    def __init__(self, initial: list[dict[str, Any]] | None = None) -> None:
        self.messages = list(initial or [])
        self.min_ids: list[int] = []
        self.failures: dict[int, tuple[int, BaseException]] = {}
        self.link_errors: dict[str, Exception] = {}
        self.resolved_links: list[str] = []
        self.title_ids: tuple[int, ...] = (SOURCE_ID,)
        self.title_lookups = 0
        self.honour_min_id = True
        self.started = 0
        self.closed = 0

    def fail_pass(self, number: int, after: int, error: BaseException) -> None:
        """Make the number-th iter_messages call raise error after yielding `after` messages."""
        self.failures[number] = (after, error)

    def start(self) -> None:
        self.started += 1

    def close(self) -> None:
        self.closed += 1

    def get_group_title(self, chat_id: int) -> str:
        return "Ish e'lonlari"

    def iter_group_ids_by_title(self, title: str) -> Iterator[int]:
        self.title_lookups += 1
        yield from self.title_ids

    def resolve_group_link(self, link: str | None) -> int | None:
        if not link:
            return None
        self.resolved_links.append(link)
        if link in self.link_errors:
            raise self.link_errors[link]
        match = re.search(r"t\.me/c/(\d+)", link)
        return int(f"-100{match.group(1)}") if match else None

    def iter_messages(self, chat_id: int, limit: int | None = None, min_id: int = 0) -> Iterator[dict[str, Any]]:
        self.min_ids.append(min_id)
        after, error = self.failures.get(len(self.min_ids), (None, None))
        floor = min_id if self.honour_min_id else 0
        newest_first = sorted((m for m in self.messages if m["id"] > floor), key=lambda m: m["id"], reverse=True)
        for index, message in enumerate(newest_first):
            if index == after:
                raise error
            yield message
        if after is not None:
            raise error


class CrawlerTestCase(unittest.TestCase):
    """Point the crawler at a temporary RAW_DATA_DIR and capture its output."""

    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="crawler-test-")))
        self.raw_dir = root / "raw"
        data_dir = (PROJECT_ROOT / "data").resolve()
        self.assertFalse(self.raw_dir.resolve().is_relative_to(data_dir), "tests must never write under data/")
        self.settings = dataclasses.replace(
            crawler.settings,
            telegram_api_id=0,
            telegram_api_hash="",
            telegram_phone_number="",
            source_group_id=SOURCE_ID,
            source_group_title="Ish e'lonlari",
            tdlib_database_dir=root / "tdlib",
            raw_data_dir=self.raw_dir,
            request_delay_seconds=0.0,
            crawl_until_timestamp=None,
        )
        self.use_settings()
        self.checkpoint_path = self.raw_dir / ".state" / f"source_{SOURCE_ID}.json"
        crawler._unresolvable_links.clear()
        self.addCleanup(crawler._unresolvable_links.clear)
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.stdout))
        self.enterContext(contextlib.redirect_stderr(self.stderr))

    def use_settings(self, **changes: Any) -> None:
        self.settings = dataclasses.replace(self.settings, **changes)
        self.enterContext(mock.patch.object(crawler, "settings", self.settings))

    def checkpoint(self) -> int:
        return load_checkpoint(self.checkpoint_path)

    def stored(self) -> dict[str, list[int]]:
        """Return message ids per JSONL file, in file order."""
        return {
            path.name: [json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines()]
            for path in sorted(self.raw_dir.glob("*.jsonl"))
        }

    def stored_ids(self) -> list[int]:
        return sorted(message_id for ids in self.stored().values() for message_id in ids)

    def run_main(self, argv: list[str], client: FakeClient, on_sleep: Callable[[int], None] | None = None) -> mock.Mock:
        """Run crawler.main with the fake client; time.sleep calls on_sleep(call_number) instead of sleeping."""
        calls = 0

        def fake_sleep(seconds: float) -> None:
            nonlocal calls
            calls += 1
            if on_sleep is not None:
                on_sleep(calls)

        with (
            mock.patch.object(crawler, "TdlibClient", return_value=client) as factory,
            mock.patch.object(crawler.time, "sleep", side_effect=fake_sleep) as sleep,
        ):
            try:
                crawler.main(argv)
            except KeyboardInterrupt:
                self.fail("Ctrl+C escaped main() instead of stopping the loop cleanly")
        factory.assert_called_once_with(
            api_id=0, api_hash="", phone_number="", database_directory=self.settings.tdlib_database_dir
        )
        return sleep


class CheckpointTests(CrawlerTestCase):
    def test_checkpoint_is_highest_id_after_pass(self) -> None:
        client = FakeClient(messages(101, 110))
        self.assertEqual(crawler.crawl_group(client, SOURCE_ID), 10)
        self.assertEqual(self.checkpoint(), 110)
        self.assertEqual(self.stored(), {DESTINATION_FILE: list(range(110, 100, -1))})
        self.assertEqual(client.min_ids, [0])

    def test_pass_without_new_messages_appends_nothing(self) -> None:
        client = FakeClient(messages(101, 110))
        crawler.crawl_group(client, SOURCE_ID)
        before = (self.raw_dir / DESTINATION_FILE).read_bytes()
        self.assertEqual(crawler.crawl_group(client, SOURCE_ID), 0)
        self.assertEqual((self.raw_dir / DESTINATION_FILE).read_bytes(), before)
        self.assertEqual(client.min_ids, [0, 110])
        self.assertEqual(self.checkpoint(), 110)
        self.assertIn("Saved 0 new source messages from Ish e'lonlari", self.stdout.getvalue())

    def test_next_pass_appends_only_new_messages(self) -> None:
        client = FakeClient(messages(101, 110))
        crawler.crawl_group(client, SOURCE_ID)
        client.messages += messages(111, 113)
        self.assertEqual(crawler.crawl_group(client, SOURCE_ID), 3)
        self.assertEqual(self.stored_ids(), list(range(101, 114)))
        self.assertEqual(self.checkpoint(), 113)
        self.assertEqual(client.min_ids, [0, 110])

    def test_interrupted_pass_leaves_checkpoint_unchanged(self) -> None:
        for error in (ConnectionError("connection lost"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                save_checkpoint(self.checkpoint_path, 100)
                for path in self.raw_dir.glob("*.jsonl"):
                    path.unlink()
                client = FakeClient(messages(101, 110))
                client.fail_pass(1, after=4, error=error)
                with self.assertRaises(type(error)):
                    crawler.crawl_group(client, SOURCE_ID)
                self.assertEqual(self.stored_ids(), [107, 108, 109, 110])
                self.assertEqual(self.checkpoint(), 100)

                self.assertEqual(crawler.crawl_group(client, SOURCE_ID), 10)
                self.assertEqual(client.min_ids, [100, 100])
                self.assertEqual(sorted(set(self.stored_ids())), list(range(101, 111)))
                self.assertEqual(self.checkpoint(), 110)
        self.assertIn("ERROR while crawling Ish e'lonlari", self.stderr.getvalue())

    def test_checkpoint_never_moves_backwards(self) -> None:
        save_checkpoint(self.checkpoint_path, 200)
        client = FakeClient(messages(150, 160))
        client.honour_min_id = False
        self.assertEqual(crawler.crawl_group(client, SOURCE_ID), 0)
        self.assertEqual(self.checkpoint(), 200)
        self.assertEqual(self.stored(), {})

    def test_crawl_until_break_saves_highest_id(self) -> None:
        self.use_settings(crawl_until_timestamp=START + 106 * 60)
        client = FakeClient(messages(101, 110))
        self.assertEqual(crawler.crawl_group(client, SOURCE_ID), 5)
        self.assertEqual(self.stored_ids(), list(range(106, 111)))
        self.assertEqual(self.checkpoint(), 110)

    def test_routing_is_unchanged(self) -> None:
        client = FakeClient([
            source_message(101, group=None),
            source_message(102, link=None),
            source_message(103),
            source_message(104, link="https://t.me/daeso_jobs"),
        ])
        self.assertEqual(crawler.crawl_group(client, SOURCE_ID), 4)
        self.assertEqual(
            self.stored(),
            {
                DESTINATION_FILE: [103],
                "group_unmatched_Daeso_arbayt.jsonl": [104, 102],
                "group_unmatched_unknown.jsonl": [101],
            },
        )
        stored_raw = json.loads((self.raw_dir / DESTINATION_FILE).read_text(encoding="utf-8"))
        self.assertEqual(stored_raw, json.loads(source_message(103)["raw_message_json"]))
        output = self.stdout.getvalue()
        self.assertIn("Crawling source group: Ish e'lonlari (-1009000000001)", output)
        self.assertIn("Saved 4 new source messages from Ish e'lonlari", output)
        self.assertIn("  Monthly totals: 2026-10: 4", output)
        self.assertIn("  Routed groups: Daeso arbayt: 2, -1001987654321: 1, unmatched: 1", output)

    def test_link_rejected_by_telegram_routes_to_unmatched(self) -> None:
        errors = {
            "ValueError": ValueError('No user has "gone_group" as username'),
            "UsernameInvalidError": UsernameInvalidError(request=None),
        }
        for name, error in errors.items():
            with self.subTest(error=name):
                link = f"https://t.me/{name.lower()}_group"
                start = 100 + 10 * len(self.stored_ids()) + 1
                client = FakeClient(messages(start, start + 2, group="Yopiq Guruh", link=link))
                client.link_errors[link] = error
                save_checkpoint(self.checkpoint_path, start - 1)
                self.assertEqual(crawler.crawl_group(client, SOURCE_ID), 3)
                self.assertEqual(client.resolved_links, [link])
                self.assertEqual(self.checkpoint(), start + 2)
                self.assertIn(f"Cannot resolve group link {link}", self.stderr.getvalue())
        self.assertEqual(list(self.stored()), ["group_unmatched_Yopiq_Guruh.jsonl"])

    def test_transient_link_error_fails_the_pass(self) -> None:
        client = FakeClient(messages(101, 103))
        client.link_errors[DESTINATION_LINK] = ConnectionError("network down")
        with self.assertRaises(ConnectionError):
            crawler.crawl_group(client, SOURCE_ID)
        self.assertEqual(self.checkpoint(), 0)
        self.assertEqual(self.stored(), {})


class CommandLineTests(CrawlerTestCase):
    def test_every_below_minimum_is_rejected(self) -> None:
        for value in ("29", "0", "-60", "abc", "45.5", ""):
            with (
                self.subTest(value=value),
                mock.patch.object(crawler, "TdlibClient") as factory,
                mock.patch.object(crawler.time, "sleep", side_effect=KeyboardInterrupt),
            ):
                with self.assertRaises(SystemExit) as raised:
                    crawler.main(["--every", value])
                self.assertEqual(raised.exception.code, 2)
                factory.assert_not_called()
        errors = self.stderr.getvalue()
        self.assertIn("argument --every: must be at least 30 seconds, got 29", errors)
        self.assertIn("argument --every: expected whole seconds, got 'abc'", errors)
        self.assertFalse(self.raw_dir.exists())

    def test_every_accepts_minimum(self) -> None:
        self.assertEqual(crawler.parse_args(["--every", "30"]).every, 30)
        self.assertEqual(crawler.parse_args(["--every=3600"]).every, 3600)
        self.assertIsNone(crawler.parse_args([]).every)

    def test_default_is_a_single_pass(self) -> None:
        client = FakeClient(messages(101, 110))
        sleep = self.run_main([], client)
        sleep.assert_not_called()
        self.assertEqual((client.started, client.closed), (1, 1))
        self.assertEqual(client.min_ids, [0])
        self.assertEqual(self.checkpoint(), 110)

    def test_single_pass_failure_raises_and_closes_client(self) -> None:
        client = FakeClient(messages(101, 110))
        client.fail_pass(1, after=2, error=ConnectionError("connection lost"))
        with self.assertRaises(ConnectionError):
            self.run_main([], client)
        self.assertEqual(client.closed, 1)
        self.assertEqual(self.checkpoint(), 0)

    def test_single_pass_unknown_source_title_raises(self) -> None:
        self.use_settings(source_group_id=None)
        client = FakeClient(messages(101, 102))
        client.title_ids = ()
        with self.assertRaisesRegex(ValueError, "Source group not found: \"Ish e'lonlari\""):
            self.run_main([], client)
        self.assertEqual(client.closed, 1)


class LoopTests(CrawlerTestCase):
    def test_loop_runs_passes_and_survives_a_failing_pass(self) -> None:
        client = FakeClient(messages(101, 105))
        client.fail_pass(2, after=1, error=ConnectionError("connection lost"))

        def on_sleep(call: int) -> None:
            if call == 1:
                client.messages += messages(106, 108)
            if call == 3:
                raise KeyboardInterrupt

        sleep = self.run_main(["--every", "60"], client, on_sleep)
        self.assertEqual(sleep.call_args_list, [mock.call(60)] * 3)
        self.assertEqual((client.started, client.closed), (1, 1))
        self.assertEqual(client.min_ids, [0, 105, 105])
        self.assertEqual(self.checkpoint(), 108)
        self.assertEqual(sorted(set(self.stored_ids())), list(range(101, 109)))
        output = self.stdout.getvalue()
        self.assertRegex(output, r"\] Pass 1: 5 new messages in \d+\.\d s; next pass in 60 s")
        self.assertRegex(output, r"\] Pass 3: 3 new messages in \d+\.\d s; next pass in 60 s")
        self.assertIn("Stopped after 3 passes; 8 new messages saved in this run.", output)
        self.assertRegex(
            self.stderr.getvalue(), r"\] Pass 2 failed \(ConnectionError: connection lost\); retrying in 60 s"
        )

    def test_ctrl_c_during_a_pass_exits_cleanly(self) -> None:
        save_checkpoint(self.checkpoint_path, 100)
        client = FakeClient(messages(101, 110))
        client.fail_pass(1, after=3, error=KeyboardInterrupt())
        sleep = self.run_main(["--every", "30"], client)
        sleep.assert_not_called()
        self.assertEqual(client.closed, 1)
        self.assertEqual(self.checkpoint(), 100)
        self.assertIn("Stopped after 0 passes; 0 new messages saved in this run.", self.stdout.getvalue())

    def test_loop_retries_source_lookup_then_reuses_it(self) -> None:
        self.use_settings(source_group_id=None)
        client = FakeClient(messages(101, 103))
        client.title_ids = ()

        def on_sleep(call: int) -> None:
            if call == 1:
                client.title_ids = (SOURCE_ID,)
            if call == 3:
                raise KeyboardInterrupt

        self.run_main(["--every", "30"], client, on_sleep)
        self.assertEqual(client.title_lookups, 2)
        self.assertEqual(client.min_ids, [0, 103])
        self.assertEqual(self.checkpoint(), 103)
        self.assertIn("Pass 1 failed (ValueError: Source group not found", self.stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
