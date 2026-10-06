"""Dashboard API tests on synthetic JSONL files in temp dirs (never data/raw)."""

import asyncio
import json
import sys
import tempfile
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from src.api.config import ApiConfig
from src.api.events import Broadcaster
from src.api.main import create_app
from src.api.store import PROVINCE_IDS, Store

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
HOME_FILE = "group_-1009000000001.jsonl"    # home location Gyeonggi-do / Hwaseong in the test csv
OTHER_FILE = "group_-1009000000002.jsonl"   # not in the csv
FACTORY = "Seulda zavodga ishchi kerak, E-9 viza bilan, kuniga 130 ming, tel 010-1234-5678"
FISHING = "Busan baliq kemada ish bor, kuniga 150 ming, yotoqxona beriladi"
PLAIN = "Ish bor, batafsil lichkaga yozing, yaxshi sharoit va doimiy ish"
FORWARDED = (
    "Yangi xabar ma'lumotlari:\nGuruh: Daegu ishlar\nXabar egasi: Ali\nXabar vaqti: 2026-10-02 10:00\n"
    "Xabar matni:\nDaeguda 공장 ish, oylik 2.800.000 won, D-2 ham bo'ladi"
)


def message(msg_id: int, text: str, when: datetime) -> str:
    return json.dumps({"id": msg_id, "date": when.isoformat(sep=" "), "message": text}, ensure_ascii=False) + "\n"


class TempData:
    """A raw dir, cache dir and groups csv under one temp dir."""

    def __init__(self, directory: Path):
        self.raw = directory / "raw"
        self.raw.mkdir()
        self.groups_csv = directory / "telegram_groups.csv"
        self.groups_csv.write_text(
            "group_id,group_title,message_count,last_msg_date,province,city\n"
            "-1009000000001,Hwaseong ishlari,4,2026-10-03 00:00:00+00:00,Gyeonggi-do,Hwaseong\n",
            encoding="utf-8",
        )
        self.config = ApiConfig(raw_dir=self.raw, cache_dir=directory / "cache", groups_csv=self.groups_csv,
                                frontend_dist=directory / "dist", poll_seconds=0.05, workers=1)

    def append(self, name: str, *lines: str) -> None:
        with (self.raw / name).open("a", encoding="utf-8") as target:
            target.write("".join(lines))

    def seed(self) -> None:
        self.append(HOME_FILE,
                    message(1, FACTORY, NOW - timedelta(hours=2)),
                    message(2, PLAIN, NOW - timedelta(days=3)),
                    message(3, FORWARDED, NOW - timedelta(hours=30)))
        self.append(OTHER_FILE,
                    message(10, FISHING, NOW - timedelta(days=40)),
                    message(11, FACTORY, NOW - timedelta(hours=20)))  # repost of message 1 in another group


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = TempData(Path(self.temp.name))
        self.data.seed()

    def tearDown(self):
        self.temp.cleanup()

    def loaded_store(self) -> Store:
        store = Store(self.data.config)
        store.load()
        return store

    def test_reposts_keep_the_oldest_copy_even_when_it_arrives_later(self):
        store = self.loaded_store()
        self.assertEqual((len(store.snapshot.posts), len(store.snapshot.ads)), (5, 4))
        factory = store.snapshot.ads.set_index("row_id").loc[f"{OTHER_FILE}:11"]
        self.assertEqual(factory["repost_count"], 2)

        self.data.append(HOME_FILE, message(4, FACTORY, NOW - timedelta(days=30)))  # backfilled older copy
        update = store.poll()
        self.assertEqual((update["added_posts"], update["added_ads"]), (1, 0))
        ads = store.snapshot.ads.set_index("row_id")
        self.assertIn(f"{HOME_FILE}:4", ads.index)
        self.assertNotIn(f"{OTHER_FILE}:11", ads.index)
        self.assertEqual(ads.loc[f"{HOME_FILE}:4", "repost_count"], 3)

    def test_partial_last_line_waits_for_its_newline(self):
        store = self.loaded_store()
        line = message(5, FISHING + " yangi", NOW)
        self.data.append(HOME_FILE, line[:30])
        self.assertIsNone(store.poll())
        self.data.append(HOME_FILE, line[30:])
        self.assertEqual(store.poll()["added_posts"], 1)
        self.assertEqual(len(store.snapshot.posts), 6)

    def test_repeated_message_id_is_ignored(self):
        store = self.loaded_store()
        self.data.append(HOME_FILE, message(1, FACTORY, NOW - timedelta(hours=2)))
        self.assertIsNone(store.poll())
        self.assertEqual(len(store.snapshot.posts), 5)

    def test_truncated_file_is_read_again(self):
        store = self.loaded_store()
        (self.data.raw / OTHER_FILE).write_text(message(20, PLAIN + " qayta", NOW), encoding="utf-8")
        store.poll()
        rows = store.snapshot.posts.loc[store.snapshot.posts["source_file"] == OTHER_FILE, "row_id"]
        self.assertEqual(rows.tolist(), [f"{OTHER_FILE}:20"])

    def test_cache_reload_then_reads_only_new_lines(self):
        store = self.loaded_store()
        self.assertTrue(store.cache_path.is_file())
        self.data.append(OTHER_FILE, message(12, PLAIN + " ertaga", NOW))
        restored = Store(self.data.config)
        self.assertTrue(restored._restore_cache())
        self.assertEqual(len(restored.snapshot.posts), 5)
        restored.load()
        self.assertEqual(len(restored.snapshot.posts), 6)
        self.assertEqual(restored.snapshot.version, store.snapshot.version + 1)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = TempData(Path(self.temp.name))
        self.data.seed()
        self.app = create_app(self.data.config, now=lambda: NOW)
        self.client = TestClient(self.app)
        self.client.__enter__()
        deadline = time.monotonic() + 10
        while self.client.get("/api/health").json()["status"] != "ready":
            self.assertLess(time.monotonic(), deadline, "store did not load")
            time.sleep(0.02)

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def get(self, path: str, status: int = 200) -> dict:
        response = self.client.get(path)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def test_every_endpoint_has_the_contract_shape(self):
        expected = {
            "/api/meta": {"version", "provinces", "date_min", "date_max", "groups"},
            "/api/overview": {"version", "kpis", "volume", "top_provinces"},
            "/api/locations": {"version", "total", "provinces", "unplaced", "sources"},
            "/api/regions/Seoul": {"version", "province", "name_ko", "ads", "rank", "share", "trend", "by_source",
                                   "cities", "pay", "occupations", "visas", "scripts", "groups", "latest"},
            "/api/feed": {"version", "items"},
            "/api/pay": {"version", "periods", "trend", "by_province"},
            "/api/jobs": {"version", "named_share", "visa_share", "occupations", "visas", "matrix"},
            "/api/posts": {"version", "scripts", "flags", "length", "reposts"},
            "/api/groups": {"version", "groups"},
        }
        for path, keys in expected.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertNotIn("NaN", response.text)
                self.assertEqual(set(response.json()), keys)

    def test_overview_and_locations_numbers(self):
        overview = self.get("/api/overview")
        kpis = overview["kpis"]
        self.assertEqual((kpis["unique_ads"], kpis["posts"], kpis["last_24h"], kpis["last_7d"]), (4, 5, 1, 3))
        self.assertEqual(kpis["median_pay"], {"hourly": None, "daily": 140000, "monthly": 2800000})
        self.assertEqual(overview["volume"]["granularity"], "month")

        locations = self.get("/api/locations")
        self.assertEqual(len(locations["provinces"]), len(PROVINCE_IDS))
        counts = {row["province"]: row["ads"] for row in locations["provinces"] if row["ads"]}
        self.assertEqual(counts, {"Seoul": 1, "Busan": 1, "Daegu": 1, "Gyeonggi-do": 1})
        self.assertEqual(locations["sources"], {"address": 0, "text": 3, "group": 1, "unknown": 0})

    def test_filters(self):
        self.assertEqual(self.get("/api/overview?source=forwarded")["kpis"]["unique_ads"], 1)
        self.assertEqual(self.get("/api/overview?source=direct")["kpis"]["unique_ads"], 3)
        recent = self.get("/api/overview?days=7")
        self.assertEqual(recent["kpis"]["unique_ads"], 3)
        self.assertEqual((recent["volume"]["granularity"], len(recent["volume"]["points"])), ("day", 8))
        by_post = self.get("/api/locations?basis=post")
        self.assertEqual(by_post["unplaced"]["group_fallback"], 1)
        self.assertEqual(sum(row["ads"] for row in by_post["provinces"]), 3)

    def test_region_feed_and_errors(self):
        region = self.get("/api/regions/Seoul")
        self.assertEqual((region["ads"], region["latest"][0]["visas"]), (1, ["E-9"]))
        self.assertEqual(region["latest"][0]["repost_count"], 2)
        self.assertEqual(self.get("/api/regions/Atlantis", 404), {"detail": "Unknown region"})
        self.get("/api/feed?province=Atlantis", 404)
        for bad in ("days=0", "source=bots", "basis=group"):
            self.get(f"/api/overview?{bad}", 422)
        self.get("/api/feed?limit=101", 422)

        items = self.get("/api/feed?limit=2")["items"]
        self.assertEqual([item["date"] for item in items], sorted((item["date"] for item in items), reverse=True))
        forwarded = self.get("/api/feed?source=forwarded")["items"][0]
        self.assertEqual((forwarded["group_title"], forwarded["is_forwarded"]), ("Daegu ishlar", True))
        self.assertNotIn("Ali", json.dumps(forwarded))

    def test_new_lines_bump_the_version(self):
        version = self.get("/api/health")["version"]
        self.data.append(OTHER_FILE, message(13, "Incheon 물류 창고 ish, soatiga 12.000 won", NOW))
        deadline = time.monotonic() + 5
        while self.get("/api/health")["version"] == version:
            self.assertLess(time.monotonic(), deadline, "poller did not pick up the new line")
            time.sleep(0.02)
        self.assertEqual(self.get("/api/overview")["kpis"]["unique_ads"], 5)


class LoadingTests(unittest.TestCase):
    def test_stats_answer_503_until_the_store_is_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            client = TestClient(create_app(TempData(Path(directory)).config))  # lifespan not started: still loading
            self.assertEqual(client.get("/api/health").json()["status"], "loading")
            response = client.get("/api/overview")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"status": "loading", "progress": 0.0})


class EventTests(unittest.TestCase):
    def test_update_event_reaches_subscribers_and_close_ends_the_stream(self):
        async def scenario() -> list[str]:
            with tempfile.TemporaryDirectory() as directory:
                data = TempData(Path(directory))
                data.seed()
                broadcaster = Broadcaster()
                broadcaster.bind(asyncio.get_running_loop())
                store = Store(data.config, on_update=lambda update: broadcaster.publish("update", update))
                await asyncio.to_thread(store.load)
                stream = broadcaster.stream(lambda: {"version": store.snapshot.version, "status": store.status})
                received = [await anext(stream)]
                data.append(HOME_FILE, message(6, FISHING + " Incheon", NOW))
                await asyncio.to_thread(store.poll)
                received.append(await asyncio.wait_for(anext(stream), timeout=5))
                broadcaster.close()
                received += [chunk async for chunk in stream]
                return received

        hello, update, *rest = asyncio.run(scenario())
        self.assertTrue(hello.startswith("event: hello\n"))
        self.assertTrue(update.startswith("event: update\n"))
        payload = json.loads(update.split("data: ", 1)[1])
        self.assertEqual((payload["version"], payload["added_posts"]), (2, 1))
        self.assertEqual(rest, [])


if __name__ == "__main__":
    unittest.main()
