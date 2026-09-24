"""Plain-text storage for raw Telegram messages."""

from pathlib import Path
from collections.abc import Iterable

from src.crawler.messages import MessageRecord


def ensure_raw_directory(directory: Path) -> None:
    """Create the raw data directory when it does not exist."""
    directory.mkdir(parents=True, exist_ok=True)


def write_messages(path: Path, messages: Iterable[MessageRecord]) -> None:
    """Write normalized messages as one readable record per block."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        for message in messages:
            output.write(f"[{message.date or ''}] {message.chat_id}/{message.message_id}\n")
            output.write(message.text)
            output.write("\n\n")
