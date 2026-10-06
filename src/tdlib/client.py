"""Telegram client boundary used by the crawler."""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import datetime
import json
import re
from pathlib import Path
from typing import Any

from telethon import events
from telethon.errors import BadRequestError
from telethon.sync import TelegramClient

from src.tdlib.cache import LookupCache


def parse_group_link(link: str) -> tuple[str, int | str] | None:
    """('id', chat_id) for t.me/c/<id> links, ('username', name) for public links, else None."""
    direct_match = re.search(r"(?:t\.me|telegram\.me)/c/(\d+)", link)
    if direct_match:
        return "id", int(f"-100{direct_match.group(1)}")
    username_match = re.search(r"(?:t\.me|telegram\.me)/([A-Za-z0-9_]+)", link)
    return ("username", username_match.group(1)) if username_match else None


def message_dict(message: Any, chat_id: int) -> dict[str, Any]:
    """A Telethon message in the shape expected by the crawler."""
    raw_message = message.to_dict()
    reply_to = getattr(message, "reply_to", None)
    return {
        "id": message.id,
        "chat_id": chat_id,
        "date": int(message.date.timestamp()) if isinstance(message.date, datetime) else None,
        "message_user_id": message.sender_id,
        "reply_to_message_id": getattr(reply_to, "reply_to_msg_id", None),
        "edit_date": int(message.edit_date.timestamp()) if isinstance(message.edit_date, datetime) else None,
        "views": message.views,
        "forwards": message.forwards,
        "media_type": type(message.media).__name__ if message.media is not None else "",
        "raw_message_json": json.dumps(raw_message, default=str, ensure_ascii=False),
        "content": {
            "@type": "messageText",
            "text": {"text": message.message or ""},
        },
    }


class TdlibClient:
    """Manage a persistent Telegram user session and expose crawler operations.

    With a LookupCache, link resolutions and group titles are kept on disk, so Telegram is asked
    for each of them only once, also across runs.
    """

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        phone_number: str,
        database_directory: Path,
        cache: LookupCache | None = None,
    ) -> None:
        session_directory = Path(database_directory)
        session_directory.mkdir(parents=True, exist_ok=True)
        self._phone_number = phone_number
        self._client = TelegramClient(str(session_directory / "telegram"), api_id, api_hash)
        self._cache = cache
        self._resolved_group_links: dict[str, int | None] = dict(cache.links) if cache else {}

    def start(self) -> None:
        """Start the client connection."""
        if not self._phone_number.strip():
            raise ValueError("TELEGRAM_PHONE_NUMBER must not be empty")
        self._client.start(phone=self._phone_number)

    async def start_async(self) -> None:
        """Start the client from an already-running asyncio event loop."""
        if not self._phone_number.strip():
            raise ValueError("TELEGRAM_PHONE_NUMBER must not be empty")
        await self._client.start(phone=self._phone_number)

    async def connect_authorized_async(self) -> bool:
        """Connect without ever prompting for a login code; False when the session is not logged in."""
        await self._client.connect()
        return await self._client.is_user_authorized()

    @property
    def disconnected(self) -> asyncio.Future:
        """Resolves when the connection to Telegram is lost for good."""
        return self._client.disconnected

    def iter_joined_group_ids(self) -> Iterator[int]:
        """Yield IDs for all groups and supergroups joined by the account."""
        for dialog in self._client.iter_dialogs():
            if dialog.is_group:
                yield dialog.id

    async def joined_group_ids_async(self) -> list[int]:
        """Return joined group IDs from an already-running asyncio loop."""
        dialogs = await self._client.get_dialogs()
        return [dialog.id for dialog in dialogs if dialog.is_group]

    def iter_target_group_ids(self, configured_ids: tuple[int, ...]) -> Iterator[int]:
        """Use configured groups, or discover every joined group when unset."""
        if configured_ids:
            yield from configured_ids
            return
        yield from self.iter_joined_group_ids()

    def iter_group_ids_by_title(self, title: str) -> Iterator[int]:
        """Yield joined group IDs whose title matches case-insensitively."""
        expected = title.strip().casefold()
        for dialog in self._client.iter_dialogs():
            if dialog.is_group and dialog.name.strip().casefold() == expected:
                yield dialog.id

    async def joined_chat_ids_async(self) -> set[int]:
        """IDs of every group and channel the account is a member of (Telegram pushes only these)."""
        dialogs = await self._client.get_dialogs()
        return {dialog.id for dialog in dialogs if dialog.is_group or dialog.is_channel}

    async def can_read_async(self, chat_id: int) -> bool:
        """True when the chat's messages can be requested without joining it.

        Checks the session first (no request); otherwise resolves the chat's public username, if a link
        to it was seen, once: Telethon keeps it in the session, so later runs need no request.
        """
        try:
            await self._client.get_input_entity(chat_id)
            return True
        except (ValueError, TypeError):
            pass
        bare_id = int(str(chat_id).removeprefix("-100"))
        for link, linked_id in self._resolved_group_links.items():
            parsed = parse_group_link(link)
            if linked_id not in (chat_id, bare_id) or parsed is None or parsed[0] != "username":
                continue
            try:
                await self._client.get_entity(parsed[1])
                return True
            except (ValueError, BadRequestError):
                continue
        return False

    async def group_ids_by_title_async(self, title: str) -> list[int]:
        """Joined group IDs whose title matches case-insensitively, from a running loop."""
        expected = title.strip().casefold()
        dialogs = await self._client.get_dialogs()
        return [dialog.id for dialog in dialogs if dialog.is_group and dialog.name.strip().casefold() == expected]

    def get_group_title(self, chat_id: int) -> str:
        """Return a human-readable title for a group ID."""
        if self._cache and (cached := self._cache.title(chat_id)):
            return cached
        entity = self._client.get_entity(chat_id)
        return self._remember_title(chat_id, entity)

    async def get_group_title_async(self, chat_id: int) -> str:
        """Return a group title from an already-running asyncio loop."""
        if self._cache and (cached := self._cache.title(chat_id)):
            return cached
        entity = await self._client.get_entity(chat_id)
        return self._remember_title(chat_id, entity)

    def _remember_title(self, chat_id: int, entity: Any) -> str:
        title = str(getattr(entity, "title", None) or getattr(entity, "first_name", None) or chat_id)
        if self._cache:
            self._cache.set_title(chat_id, title)
        return title

    def resolve_group_link(self, link: str | None) -> int | None:
        """Resolve a public Telegram group link once and cache its chat ID."""
        if not link:
            return None
        if link in self._resolved_group_links:
            return self._resolved_group_links[link]
        parsed = parse_group_link(link)
        if parsed is None or parsed[0] == "id":
            return self._remember_link(link, parsed[1] if parsed else None)
        try:
            entity = self._client.get_entity(parsed[1])
        except (ValueError, BadRequestError):
            self._remember_link(link, None)  # Telegram rejected it: never ask again
            raise
        return self._remember_link(link, getattr(entity, "id", None))

    async def resolve_group_link_async(self, link: str | None) -> int | None:
        """resolve_group_link from an already-running asyncio loop (same cache)."""
        if not link:
            return None
        if link in self._resolved_group_links:
            return self._resolved_group_links[link]
        parsed = parse_group_link(link)
        if parsed is None or parsed[0] == "id":
            return self._remember_link(link, parsed[1] if parsed else None)
        try:
            entity = await self._client.get_entity(parsed[1])
        except (ValueError, BadRequestError):
            self._remember_link(link, None)
            raise
        return self._remember_link(link, getattr(entity, "id", None))

    def _remember_link(self, link: str, chat_id: Any) -> int | None:
        value = int(chat_id) if isinstance(chat_id, int) else None
        self._resolved_group_links[link] = value
        if self._cache:
            self._cache.set_link(link, value)
        return value

    async def close_async(self) -> None:
        """Close the client from an already-running asyncio event loop."""
        await self._client.disconnect()

    def iter_messages(
        self, chat_id: int, limit: int | None = None, min_id: int = 0
    ) -> Iterator[dict[str, Any]]:
        """Yield messages newer than min_id in the shape expected by the crawler."""
        if limit is not None and limit < 1:
            return
        for message in self._client.iter_messages(chat_id, limit=limit, min_id=min_id):
            yield message_dict(message, chat_id)

    async def iter_messages_async(
        self, chat_id: int, limit: int | None = None, min_id: int = 0
    ) -> AsyncIterator[dict[str, Any]]:
        """iter_messages from an already-running asyncio loop (newest first)."""
        if limit is not None and limit < 1:
            return
        async for message in self._client.iter_messages(chat_id, limit=limit, min_id=min_id):
            yield message_dict(message, chat_id)

    def on_new_message(self, chat_ids: tuple[int, ...], callback: Callable[[dict[str, Any]], None]) -> None:
        """Call `callback` with every new message Telegram pushes for these chats (no polling)."""

        async def handler(event: events.NewMessage.Event) -> None:
            callback(message_dict(event.message, event.chat_id))

        self._client.add_event_handler(handler, events.NewMessage(chats=list(chat_ids)))

    def close(self) -> None:
        """Close the client connection."""
        self._client.disconnect()
