"""Helpers for turning Telegram message payloads into text records."""

from dataclasses import dataclass
import re
from pathlib import Path
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


def extract_referenced_group_name(text: str) -> str | None:
    """Extract the destination group from a structured Ish e'lonlari post."""
    match = re.search(r"(?im)^\s*\*{0,2}Guruh\*{0,2}\s*:\s*\*{0,2}(.+?)\*{0,2}\s*$", text)
    if not match:
        return None
    group_name = re.sub(r"\s+", " ", match.group(1)).strip(" *")
    return group_name or None


def extract_referenced_group_link(message: dict[str, Any]) -> str | None:
    """Extract the URL entity attached to the structured Guruh field."""
    text = str(message.get("message", ""))
    group_match = re.search(r"(?im)^\s*\*{0,2}Guruh\*{0,2}\s*:", text)
    if not group_match:
        return None

    start_utf16 = len(text[:group_match.start()].encode("utf-16-le")) // 2
    end_utf16 = len(text[:text.find("\n", group_match.start()) if "\n" in text[group_match.start():] else len(text)].encode("utf-16-le")) // 2
    for entity in message.get("entities", ()) or ():
        offset = int(entity.get("offset", 0))
        length = int(entity.get("length", 0))
        if offset >= end_utf16 or offset + length <= start_utf16:
            continue
        link = entity.get("url")
        if link:
            return str(link)
    return None


def group_filename(group_name: str) -> str:
    """Create a stable filesystem-safe name from a referenced group title."""
    safe_name = re.sub(r"[^\w\s-]", "", group_name, flags=re.UNICODE)
    safe_name = re.sub(r"[\s-]+", "_", safe_name).strip("_")
    return (safe_name or "unknown_group")[:100]


def output_path(raw_dir: Path, referenced_group_id: int | None, referenced_group: str | None) -> Path:
    """The JSONL file a post belongs in: its resolved group, else an unmatched file named after the group."""
    if referenced_group_id is None:
        return raw_dir / f"group_unmatched_{group_filename(referenced_group or 'unknown')}.jsonl"
    return raw_dir / f"group_{referenced_group_id}.jsonl"
