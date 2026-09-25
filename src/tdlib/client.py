"""Telegram client boundary used by the crawler."""

from collections.abc import Iterator
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from telethon.sync import TelegramClient


class TdlibClient:
    """Manage a persistent Telegram user session and expose crawler operations."""

    def __init__(self, api_id: int, api_hash: str, phone_number: str, database_directory: Path) -> None:
        session_directory = Path(database_directory)
        session_directory.mkdir(parents=True, exist_ok=True)
        self._phone_number = phone_number
        self._client = TelegramClient(str(session_directory / "telegram"), api_id, api_hash)

    def start(self) -> None:
        """Start the client connection."""
        if not self._phone_number.strip():
            raise ValueError("TELEGRAM_PHONE_NUMBER must not be empty")
        self._client.start(phone=self._phone_number)

    def iter_joined_group_ids(self) -> Iterator[int]:
        """Yield IDs for all groups and supergroups joined by the account."""
        for dialog in self._client.iter_dialogs():
            if dialog.is_group:
                yield dialog.id

    def iter_target_group_ids(self, configured_ids: tuple[int, ...]) -> Iterator[int]:
        """Use configured groups, or discover every joined group when unset."""
        if configured_ids:
            yield from configured_ids
            return
        yield from self.iter_joined_group_ids()

    def get_group_title(self, chat_id: int) -> str:
        """Return a human-readable title for a group ID."""
        entity = self._client.get_entity(chat_id)
        return str(getattr(entity, "title", None) or getattr(entity, "first_name", None) or chat_id)

    def iter_messages(
        self, chat_id: int, limit: int | None = None, min_id: int = 0
    ) -> Iterator[dict[str, Any]]:
        """Yield messages newer than min_id in the shape expected by the crawler."""
        if limit is not None and limit < 1:
            return
        for message in self._client.iter_messages(chat_id, limit=limit, min_id=min_id):
            raw_message = message.to_dict()
            reply_to = getattr(message, "reply_to", None)
            yield {
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

    def close(self) -> None:
        """Close the client connection."""
        self._client.disconnect()
