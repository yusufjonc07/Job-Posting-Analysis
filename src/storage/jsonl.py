"""JSONL storage for complete Telegram message objects."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from src.crawler.messages import MessageRecord


def append_messages_jsonl(path: Path, messages: Iterable[MessageRecord]) -> int:
    """Append one complete raw Telegram object per JSONL line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as output:
        for message in messages:
            try:
                raw_message: dict[str, Any] = json.loads(message.raw_message_json)
            except json.JSONDecodeError:
                raw_message = {
                    "id": message.message_id,
                    "chat_id": message.chat_id,
                    "date": message.date,
                    "text": message.text,
                }
            output.write(json.dumps(raw_message, ensure_ascii=False, default=str) + "\n")
            output.flush()
            count += 1
    return count


def append_message_jsonl(path: Path, message: MessageRecord) -> None:
    """Append one complete raw Telegram object and flush it immediately."""
    append_messages_jsonl(path, [message])


def load_checkpoint(path: Path) -> int:
    """Read the last source message ID processed by the routed collector."""
    if not path.exists():
        return 0
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("last_message_id", 0))
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0


def save_checkpoint(path: Path, message_id: int) -> None:
    """Persist a source checkpoint atomically after a message is stored."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps({"last_message_id": message_id}), encoding="utf-8")
    temporary_path.replace(path)


def last_message_id(path: Path) -> int:
    """Return the highest saved Telegram message ID from a JSONL file."""
    if not path.exists():
        return 0
    highest_id = 0
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            try:
                message_id = int(json.loads(line).get("id", 0))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            highest_id = max(highest_id, message_id)
    return highest_id
