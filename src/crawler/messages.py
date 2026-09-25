"""Helpers for turning Telegram message payloads into text records."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MessageRecord:
    """Normalized message data used by storage and later analysis."""

    message_id: int
    chat_id: int
    text: str
    date: int | None = None
    message_user_id: int | None = None
    reply_to_message_id: int | None = None
    edit_date: int | None = None
    views: int | None = None
    forwards: int | None = None
    media_type: str = ""
    raw_message_json: str = ""


def extract_text(message: dict[str, Any]) -> str:
    """Extract plain text from a TDLib message payload."""
    content = message.get("content", {})
    if content.get("@type") != "messageText":
        return ""
    text = content.get("text", {})
    return str(text.get("text", "")).strip()


def normalize_message(message: dict[str, Any]) -> MessageRecord:
    """Convert a raw message dictionary to a stable record."""
    return MessageRecord(
        message_id=int(message.get("id", 0)),
        chat_id=int(message.get("chat_id", 0)),
        text=extract_text(message),
        date=message.get("date"),
        message_user_id=message.get("message_user_id"),
        reply_to_message_id=message.get("reply_to_message_id"),
        edit_date=message.get("edit_date"),
        views=message.get("views"),
        forwards=message.get("forwards"),
        media_type=str(message.get("media_type", "")),
        raw_message_json=str(message.get("raw_message_json", "")),
    )
