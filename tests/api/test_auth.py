"""Log in with Telegram: widget signatures, session cookies, the deep-link flow and what visitors see."""

import dataclasses
import hashlib
import hmac
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
from fastapi.testclient import TestClient

from src.api.auth import COOKIE, AuthConfig, public_event, read_session, sign_session, verify_widget
from src.api.main import create_app
from test_dashboard_api import NOW, TempData

BOT_TOKEN = "123456:TEST-token"
SECRET = b"s" * 32
ME = {"id": 42, "first_name": "Yusuf", "username": "yusuf_test"}


def widget_data(user: dict, auth_date: int | None = None, token: str = BOT_TOKEN) -> dict:
    data = {**user, "auth_date": auth_date or int(time.time())}
    check = "\n".join(f"{key}={data[key]}" for key in sorted(data))
    data["hash"] = hmac.new(hashlib.sha256(token.encode()).digest(), check.encode(), hashlib.sha256).hexdigest()
    return data


class SignatureTests(unittest.TestCase):
    def test_widget_data_is_checked_with_the_bot_token(self):
        self.assertEqual(verify_widget(widget_data(ME), BOT_TOKEN)["id"], 42)
        self.assertIsNone(verify_widget({**widget_data(ME), "id": 43}, BOT_TOKEN), "a changed field breaks the signature")
        self.assertIsNone(verify_widget(widget_data(ME, token="999:other"), BOT_TOKEN), "signed for another bot")
        self.assertIsNone(verify_widget(widget_data(ME, auth_date=int(time.time()) - 3 * 86_400), BOT_TOKEN), "too old")

    def test_session_cookie_cannot_be_forged_or_outlive_its_age(self):
        cookie = sign_session(ME, SECRET, days=30)
        self.assertEqual(read_session(cookie, SECRET), ME)
        self.assertIsNone(read_session(cookie, b"x" * 32))
        body, signature = cookie.split(".")
        self.assertIsNone(read_session(body[:-2] + "AA." + signature, SECRET))
        self.assertIsNone(read_session(sign_session(ME, SECRET, days=-1), SECRET))

    def test_live_updates_lose_province_counts_for_visitors(self):
        update = {"version": 3, "added_posts": 2, "provinces": {"Seoul": 2}}
        self.assertEqual(public_event("update", update)["provinces"], {})
        self.assertEqual(update["provinces"], {"Seoul": 2}, "the shared event is not changed")


class LoginApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = TempData(Path(self.temp.name))
        self.data.seed()
        self.start(AuthConfig(bot_token=BOT_TOKEN, bot_username="jobs_login_bot", require_login=True, secret=SECRET))

    def start(self, auth: AuthConfig):
        if hasattr(self, "client"):
            self.client.__exit__(None, None, None)
        self.app = create_app(dataclasses.replace(self.data.config, auth=auth), now=lambda: NOW)
        self.client = TestClient(self.app)
        self.client.__enter__()
        deadline = time.monotonic() + 10
        while self.client.get("/api/health").json()["status"] != "ready":
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.02)

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def test_visitors_see_jobs_but_not_provinces_or_groups(self):
        me = self.client.get("/api/auth/me").json()
        self.assertEqual((me["required"], me["enabled"], me["user"], me["bot_username"]), (True, True, None, "jobs_login_bot"))
        for path in ("/api/locations", "/api/groups", "/api/regions/Seoul", "/api/feed?province=Seoul"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)
        overview = self.client.get("/api/overview").json()
        self.assertEqual(overview["kpis"]["unique_ads"], 4, "job numbers stay public")
        self.assertEqual(overview["top_provinces"], [])
        self.assertEqual(self.client.get("/api/pay").json()["by_province"], [])
        self.assertEqual(self.client.get("/api/jobs").json()["matrix"]["provinces"], [])
        items = self.client.get("/api/feed").json()["items"]
        self.assertTrue(items)
        self.assertTrue(all(i["province"] is None and i["city"] is None and i["group_title"] == "" for i in items))

    def test_widget_login_unlocks_everything_and_logout_locks_again(self):
        response = self.client.post("/api/auth/telegram", json=widget_data(ME))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "yusuf_test")
        self.assertIn(COOKIE, self.client.cookies)
        self.assertEqual(self.client.get("/api/locations").status_code, 200)
        self.assertTrue(self.client.get("/api/overview").json()["top_provinces"])
        self.assertTrue(any(i["group_title"] for i in self.client.get("/api/feed").json()["items"]))
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.get("/api/locations").status_code, 401)

    def test_bad_widget_data_is_refused(self):
        self.assertEqual(self.client.post("/api/auth/telegram", json={**widget_data(ME), "id": 7}).status_code, 401)

    def test_only_allowed_accounts_get_in(self):
        self.start(AuthConfig(bot_token=BOT_TOKEN, bot_username="jobs_login_bot", require_login=True, secret=SECRET,
                              allowed=frozenset({"someone_else"})))
        self.assertEqual(self.client.post("/api/auth/telegram", json=widget_data(ME)).status_code, 403)
        self.client.cookies.set(COOKIE, sign_session(ME, SECRET, 30))
        self.assertEqual(self.client.get("/api/locations").status_code, 403, "logged in, but not on the list")

    def test_deep_link_login(self):
        sent, updates = [], []

        def bot_api(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/getUpdates"):
                result, updates[:] = list(updates), []
                return httpx.Response(200, json={"ok": True, "result": result})
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": {}})

        self.app.state.links.transport = httpx.MockTransport(bot_api)
        link = self.client.post("/api/auth/link").json()
        self.assertTrue(link["url"].startswith("https://t.me/jobs_login_bot?start="))
        self.assertEqual(self.client.get(f"/api/auth/link/{link['token']}").json(), {"status": "pending"})

        updates.append({"update_id": 7, "message": {"text": f"/start {link['token']}", "from": {"id": 42, "first_name": "Yusuf", "username": "yusuf_test"}}})
        deadline = time.monotonic() + 5
        while (status := self.client.get(f"/api/auth/link/{link['token']}").json())["status"] == "pending":
            self.assertLess(time.monotonic(), deadline, "the bot never saw /start")
            time.sleep(0.05)
        self.assertEqual((status["status"], status["user"]["id"]), ("done", 42))
        self.assertEqual(self.client.get("/api/locations").status_code, 200)
        self.assertEqual(sent[0]["chat_id"], 42, "the bot confirms the login in Telegram")
        self.assertEqual(self.client.get(f"/api/auth/link/{link['token']}").json()["status"], "unknown", "a code works once")

    def test_without_a_bot_login_is_unavailable_but_data_stays_locked(self):
        self.start(AuthConfig(require_login=True, secret=SECRET))
        self.assertEqual(self.client.post("/api/auth/link").status_code, 503)
        self.assertEqual(self.client.get("/api/locations").status_code, 401)
        self.assertFalse(self.client.get("/api/auth/me").json()["enabled"])


if __name__ == "__main__":
    unittest.main()
