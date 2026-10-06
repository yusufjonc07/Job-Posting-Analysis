"""Log in with Telegram: who may see Telegram group details (the job map and province numbers are public).

Both ways end in the same signed session cookie (no server-side session store):

- Telegram Login Widget: the browser posts the data the widget signed; it is checked with the bot token
  (https://core.telegram.org/widgets/login#checking-authorization). The widget only works on the domain set
  for the bot with @BotFather /setdomain (never localhost).
- Deep link (works anywhere, also on localhost): the page opens t.me/<bot>?start=<one-time code>. When the
  user presses Start, the bot sees "/start <code>" (Bot API getUpdates, polled only while a login is
  pending) and the browser that asked for that code is logged in.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("src.api.auth")

COOKIE = "dashboard_session"
LINK_SECONDS = 600              # a deep-link code is valid this long
WIDGET_MAX_AGE = 86_400         # widget data older than a day is refused
POLL_TIMEOUT = 25               # Bot API long-poll timeout
USER_FIELDS = ("id", "first_name", "last_name", "username", "photo_url")


@dataclass(frozen=True)
class AuthConfig:
    bot_token: str = ""
    bot_username: str = ""
    login_domain: str = ""                      # domain set with /setdomain, enables the widget there
    allowed: frozenset[str] = frozenset()       # Telegram ids or usernames (lower case, no @); empty = anyone
    require_login: bool = False                 # province and group data only for logged-in users
    secret: bytes = field(default=b"", repr=False)
    session_days: int = 30
    secure_cookie: bool = False

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.bot_username)


def parse_allowed(value: str | None) -> frozenset[str]:
    return frozenset(item.strip().lstrip("@").lower() for item in (value or "").split(",") if item.strip())


def load_secret(path: Path) -> bytes:
    """The cookie-signing key: kept in the cache directory so sessions survive restarts."""
    try:
        return bytes.fromhex(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        secret = secrets.token_bytes(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secret.hex(), encoding="utf-8")
        os.chmod(path, 0o600)
        return secret


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign_session(user: dict[str, Any], secret: bytes, days: int) -> str:
    payload = json.dumps({"user": user, "exp": int(time.time()) + days * 86_400}, separators=(",", ":")).encode()
    return f"{_b64(payload)}.{_b64(hmac.new(secret, payload, hashlib.sha256).digest())}"


def read_session(value: str | None, secret: bytes) -> dict[str, Any] | None:
    """The user in a session cookie, or None when it is missing, forged or expired."""
    if not value or "." not in value or not secret:
        return None
    body, signature = value.split(".", 1)
    try:
        payload = _unb64(body)
        if not hmac.compare_digest(_unb64(signature), hmac.new(secret, payload, hashlib.sha256).digest()):
            return None
        data = json.loads(payload)
    except (ValueError, json.JSONDecodeError):
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data.get("user")


def verify_widget(data: dict[str, Any], bot_token: str, max_age: int = WIDGET_MAX_AGE) -> dict[str, Any] | None:
    """The Telegram user in Login Widget data, or None when the signature or the age is wrong."""
    data = {key: value for key, value in data.items() if value is not None}
    received = str(data.pop("hash", ""))
    check = "\n".join(f"{key}={data[key]}" for key in sorted(data))
    expected = hmac.new(hashlib.sha256(bot_token.encode()).digest(), check.encode(), hashlib.sha256).hexdigest()
    if not received or not hmac.compare_digest(expected, received):
        return None
    if time.time() - int(data.get("auth_date", 0)) > max_age:
        return None
    return clean_user(data)


def clean_user(data: dict[str, Any]) -> dict[str, Any]:
    user = {key: data[key] for key in USER_FIELDS if data.get(key) not in (None, "")}
    user["id"] = int(user["id"])
    return user


def is_allowed(user: dict[str, Any] | None, config: AuthConfig) -> bool:
    if user is None:
        return False
    if not config.allowed:
        return True
    return str(user["id"]) in config.allowed or str(user.get("username", "")).lower() in config.allowed


class DeepLinkLogins:
    """One-time codes for t.me/<bot>?start=<code>, confirmed when the bot receives /start <code>."""

    def __init__(self, config: AuthConfig, transport: httpx.AsyncBaseTransport | None = None):
        self.config = config
        self.transport = transport
        self.pending: dict[str, dict[str, Any]] = {}
        self._task: asyncio.Task | None = None
        self._offset = 0

    @property
    def api(self) -> str:
        return f"https://api.telegram.org/bot{self.config.bot_token}/"

    def start(self) -> dict[str, Any]:
        self._expire()
        code = secrets.token_urlsafe(24)
        self.pending[code] = {"created": time.time(), "user": None}
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._poll())
        return {"token": code, "url": f"https://t.me/{self.config.bot_username}?start={code}", "expires_in": LINK_SECONDS}

    def status(self, code: str) -> tuple[str, dict[str, Any] | None]:
        """'pending', 'done' (with the user; the code is used up), 'expired' or 'unknown'."""
        entry = self.pending.get(code)
        if entry is None:
            return "unknown", None
        if entry["user"] is not None:
            del self.pending[code]
            return "done", entry["user"]
        if time.time() - entry["created"] > LINK_SECONDS:
            del self.pending[code]
            return "expired", None
        return "pending", None

    def _expire(self) -> None:
        now = time.time()
        for code in [c for c, e in self.pending.items() if now - e["created"] > LINK_SECONDS + 60]:
            del self.pending[code]

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _poll(self) -> None:
        """Ask the Bot API for new messages, but only while somebody is logging in."""
        async with httpx.AsyncClient(transport=self.transport, timeout=POLL_TIMEOUT + 10) as http:
            while any(e["user"] is None for e in self.pending.values()):
                self._expire()
                try:
                    response = await http.get(self.api + "getUpdates", params={
                        "offset": self._offset, "timeout": POLL_TIMEOUT, "allowed_updates": '["message"]',
                    })
                    updates = response.json().get("result", []) if response.status_code == 200 else []
                    if response.status_code != 200:
                        log.warning("Telegram bot login: getUpdates answered %s %s", response.status_code, response.text[:200])
                        await asyncio.sleep(5)
                except httpx.HTTPError as error:
                    log.warning("Telegram bot login: %s", error)
                    await asyncio.sleep(5)
                    continue
                for update in updates:
                    self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
                    await self._handle(http, update.get("message") or {})
                if not updates:
                    await asyncio.sleep(0.5)  # never spin if the long poll returns at once

    async def _handle(self, http: httpx.AsyncClient, message: dict[str, Any]) -> None:
        text = str(message.get("text") or "")
        sender = message.get("from") or {}
        if not text.startswith("/start ") or "id" not in sender:
            return
        code = text.split(maxsplit=1)[1].strip()
        entry = self.pending.get(code)
        if entry is None or entry["user"] is not None or time.time() - entry["created"] > LINK_SECONDS:
            reply = "This login link has expired. Open the dashboard and press “Log in with Telegram” again."
        else:
            entry["user"] = clean_user(sender)
            allowed = is_allowed(entry["user"], self.config)
            reply = ("✅ You are logged in to the job-ads dashboard. You can go back to your browser."
                     if allowed else "This Telegram account is not allowed to see the dashboard's private data.")
        try:
            await http.post(self.api + "sendMessage", json={"chat_id": sender["id"], "text": reply})
        except httpx.HTTPError:
            pass


def public_view(name: str, data: dict[str, Any]) -> dict[str, Any]:
    """A response without Telegram group details, for visitors who are not logged in."""
    if name == "feed":
        return {**data, "items": hide_groups(data["items"])}
    if name == "region":
        return {**data, "groups": [], "latest": hide_groups(data["latest"])}
    return data


def hide_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**item, "group_title": ""} for item in items]


LOCKED_ENDPOINTS = frozenset({"groups"})
LOCKED_MESSAGE = "Log in with Telegram to see the Telegram groups"


def describe(config: AuthConfig, user: dict[str, Any] | None) -> dict[str, Any]:
    """/api/auth/me: what the page needs to show the login button or the logged-in user."""
    return {
        "required": config.require_login,
        "enabled": config.enabled,
        "user": user,
        "allowed": is_allowed(user, config),
        "bot_username": config.bot_username or None,
        "widget_domain": config.login_domain or None,
    }

