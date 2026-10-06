"""Group discovery from links in posts — with a fake Telegram, never the real one."""

import asyncio
import csv
import dataclasses
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from telethon.errors import FloodWaitError

from src import discover_groups as discovery
from src import main as crawler
from src.crawler.listen import listen

JOB_GROUP, CHAT_GROUP, FOLLOWED = -1001000000001, -1001000000002, -1001000000003
JOB_TEXT = "Ertaga zavodga 3 kishiga ish bor, kuniga 140 ming won, 010-1234-5678"
CHAT_TEXT = "Rahmat aka, tushundim"


def post_with_links(*urls: str) -> str:
    text = "Guruhlarimiz: " + " ".join(urls)
    return json.dumps({"_": "Message", "id": 1, "message": text, "entities": [{"_": "MessageEntityTextUrl", "url": urls[0]}]}) + "\n"


def history(chat_id: int, texts: list[str], newest: float) -> list[dict[str, Any]]:
    return [
        {"id": i + 1, "chat_id": chat_id, "date": int(newest - (len(texts) - i) * 60),
         "raw_message_json": json.dumps({"_": "Message", "id": i + 1, "message": text}),
         "content": {"@type": "messageText", "text": {"text": text}}}
        for i, text in enumerate(texts)
    ]


class FakeTelegram:
    def __init__(self):
        now = time.time()
        self.chats = {
            "jobgroup": {"id": JOB_GROUP, "title": "Job group", "kind": "group"},
            "chatgroup": {"id": CHAT_GROUP, "title": "Chat group", "kind": "group"},
            "followedgroup": {"id": FOLLOWED, "title": "Followed", "kind": "group"},
            "someperson": None,
        }
        self.histories = {
            JOB_GROUP: history(JOB_GROUP, [JOB_TEXT] * 8 + [CHAT_TEXT] * 92, now),
            CHAT_GROUP: history(CHAT_GROUP, [CHAT_TEXT] * 100, now),
        }
        self.resolved: list[str] = []
        self.history_requests: list[int] = []
        self.flood_on: str | None = None

    async def resolve_username_async(self, username: str):
        if username == self.flood_on:
            raise FloodWaitError(request=None, capture=3600)
        self.resolved.append(username)
        if username not in self.chats:
            raise ValueError(f'No user has "{username}" as username')
        return self.chats[username]

    async def iter_messages_async(self, chat_id: int, limit: int | None = None, min_id: int = 0):
        self.history_requests.append(chat_id)
        for message in sorted(self.histories.get(chat_id, []), key=lambda m: -m["id"])[:limit]:
            if message["id"] > min_id:
                yield message


class DiscoveryCase(unittest.IsolatedAsyncioTestCase):
    """A temp data/raw with posts linking to a few chats, and a groups csv that follows one of them."""

    async def asyncSetUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="discovery-test-")))
        self.raw = self.root / "raw"
        self.raw.mkdir()
        self.csv = self.root / "telegram_groups.csv"
        self.csv.write_text(f"group_id,group_title,message_count,last_msg_date,province,city\n{FOLLOWED},Followed,10,,Seoul,Seoul\n", encoding="utf-8")
        (self.raw / "group_-1009999999999.jsonl").write_text(
            post_with_links("https://t.me/JobGroup", "t.me/chatgroup", "https://t.me/followedgroup", "t.me/once_only")
            + post_with_links("https://t.me/jobgroup/123", "t.me/chatgroup", "t.me/followedgroup", "t.me/+PrivateInvite", "t.me/someperson", "t.me/someperson")
            + post_with_links("t.me/s/jobgroup", "t.me/jobs_helper_bot", "https://t.me/share/url?url=x"),
            encoding="utf-8",
        )
        self.logs: list[str] = []
        self.patch_pause = mock.patch.object(discovery, "PAUSE_BETWEEN_CHECKS", 0)
        self.patch_pause.start()
        self.addCleanup(self.patch_pause.stop)

    def run_discovery(self, client, **options):
        return discovery.discover(client, self.raw, self.csv, discovery.Options(**options), self.logs.append)


class DiscoveryTests(DiscoveryCase):
    def test_link_targets(self):
        cases = {
            "https://t.me/Chonan_Arbait": "username:chonan_arbait",
            "t.me/s/koreaish1": "username:koreaish1",
            "https://t.me/mokpoish/4512": "username:mokpoish",
            "https://t.me/c/1857660612/77": "id:-1001857660612",
            "https://t.me/+AbCdEf123": None,
            "https://t.me/joinchat/AAAAAE": None,
            "t.me/muslim_vegukin_bot": None,
            "https://t.me/share/url?url=x": None,
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(discovery.link_target(url), expected)

    async def test_adds_a_group_with_job_offers_and_remembers_every_check(self):
        client = FakeTelegram()
        added = await self.run_discovery(client)

        self.assertEqual([entry["id"] for entry in added], [JOB_GROUP])
        rows = {int(row["group_id"]): row for row in csv.DictReader(self.csv.open(encoding="utf-8"))}
        self.assertEqual((rows[JOB_GROUP]["group_title"], rows[JOB_GROUP]["province"], rows[JOB_GROUP]["city"]), ("Job group", "", ""))
        self.assertNotIn(CHAT_GROUP, rows, "a group of chat is not followed")
        saved = (self.raw / f"group_{JOB_GROUP}.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line)["id"] for line in saved], list(range(1, 101)), "its checked messages become its history, oldest first")
        self.assertNotIn("once_only", client.resolved, "links mentioned once are skipped")
        self.assertNotIn(FOLLOWED, client.history_requests, "a followed group is not read again")
        self.assertEqual(sorted(client.history_requests), sorted([JOB_GROUP, CHAT_GROUP]))

        again = FakeTelegram()
        self.assertEqual(await self.run_discovery(again), [])
        self.assertEqual(again.resolved + again.history_requests, [], "nothing is asked twice")

    async def test_dry_run_adds_nothing(self):
        added = await self.run_discovery(FakeTelegram(), dry_run=True)
        self.assertEqual(len(added), 1)
        self.assertNotIn(str(JOB_GROUP), self.csv.read_text(encoding="utf-8"))
        self.assertFalse((self.raw / f"group_{JOB_GROUP}.jsonl").exists())

    async def test_a_flood_wait_pauses_discovery(self):
        client = FakeTelegram()
        client.flood_on = "jobgroup"   # the most mentioned link comes first
        self.assertEqual(await self.run_discovery(client), [])
        self.assertTrue(any("asked to wait" in line for line in self.logs))
        later = FakeTelegram()
        self.assertEqual(await self.run_discovery(later), [])
        self.assertEqual(later.resolved, [], "nothing is asked while Telegram wants us to wait")

    def test_command_hands_the_check_to_a_running_listener(self):
        settings = dataclasses.replace(crawler.settings, tdlib_database_dir=self.root / "tdlib", raw_data_dir=self.raw)
        with mock.patch.object(crawler, "settings", settings), mock.patch.object(discovery, "settings", settings):
            held = crawler.acquire_session_lock()
            try:
                with mock.patch("sys.stdout"):
                    discovery.main(["--limit", "7", "--min-jobs", "3"])
            finally:
                held.close()
        options = discovery.read_request(self.raw)
        self.assertEqual((options.limit, options.min_jobs), (7, 3))
        self.assertIsNone(discovery.read_request(self.raw), "a request is handled once")


class RecursionTests(DiscoveryCase):
    """jobgroup (level 1, in our data) -> deepjob (2) -> deeper (3) -> deepest (4)."""

    def chain(self) -> FakeTelegram:
        client = FakeTelegram()
        now = time.time()
        for number, (name, next_name) in enumerate([("deepjob", "deeper"), ("deeper", "deepest"), ("deepest", None)], start=4):
            chat_id = -1001000000000 - number
            client.chats[name] = {"id": chat_id, "title": name, "kind": "group"}
            texts = [JOB_TEXT] * 6 + [CHAT_TEXT] * 93 + ([f"Bizning boshqa guruh: https://t.me/{next_name}"] if next_name else [CHAT_TEXT])
            client.histories[chat_id] = history(chat_id, texts, now)
        client.histories[JOB_GROUP] = history(JOB_GROUP, [JOB_TEXT] * 8 + [CHAT_TEXT] * 91 + ["Ish guruhimiz: t.me/deepjob"], now)
        return client

    async def test_follows_links_found_in_checked_groups_up_to_the_level(self):
        client = self.chain()
        added = await self.run_discovery(client, level=3)
        self.assertEqual({entry["title"]: entry["level"] for entry in added}, {"Job group": 1, "deepjob": 2, "deeper": 3})
        self.assertNotIn("deepest", client.resolved, "level 4 is beyond --level 3")
        state = json.loads((self.raw / ".state" / discovery.STATE_FILE).read_text(encoding="utf-8"))
        self.assertEqual(state["checked"]["username:deepjob"]["found_in"], [JOB_GROUP])

    async def test_level_one_does_not_recurse(self):
        client = self.chain()
        await self.run_discovery(client, level=1)
        self.assertNotIn("deepjob", client.resolved)

    async def test_links_found_beyond_the_limit_wait_for_the_next_run(self):
        first = self.chain()
        await self.run_discovery(first, level=3, limit=2)   # checks jobgroup and chatgroup (most mentioned)
        self.assertNotIn("deepjob", first.resolved)
        state = json.loads((self.raw / ".state" / discovery.STATE_FILE).read_text(encoding="utf-8"))
        self.assertEqual(state["pending"]["username:deepjob"]["level"], 2)
        second = self.chain()
        added = await self.run_discovery(second, level=3)
        self.assertEqual([entry["title"] for entry in added], ["deepjob", "deeper"])


class FollowNewGroupsTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_group_added_while_listening_is_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory)
            now = time.time()

            class Client:
                disconnected = asyncio.get_running_loop().create_future()

                def on_new_message(self, wanted, callback):
                    self.wanted, self.callback = wanted, callback

                async def iter_messages_async(self, chat_id, limit=None, min_id=0):
                    for message in sorted(history(chat_id, [JOB_TEXT] * 3, now), key=lambda m: -m["id"])[:limit]:
                        if message["id"] > min_id:
                            yield message

                async def resolve_group_link_async(self, link):
                    return None

            client = Client()
            offered = {"new": ((JOB_GROUP,), ())}

            async def add_groups(followed):
                return offered.pop("new", ((), ()))

            stop = asyncio.Event()
            with mock.patch("src.crawler.listen.HOUSEKEEPING_SECONDS", 0.05):
                task = asyncio.create_task(listen(client, (), raw, None, 3600, lambda _: None, stop, add_groups=add_groups))
                await asyncio.sleep(0.3)
                self.assertTrue(client.wanted(JOB_GROUP), "a joined group added later gets pushed messages")
                stop.set()
                await asyncio.wait_for(task, 5)
            lines = (raw / f"group_{JOB_GROUP}.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 3, "it caught up on its recent messages")


if __name__ == "__main__":
    unittest.main()
