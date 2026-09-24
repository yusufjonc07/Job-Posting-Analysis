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
    )
