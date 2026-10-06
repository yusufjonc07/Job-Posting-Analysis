"""Telegram lookups saved to disk, so each one is requested from Telegram only once across runs."""

import json
import os
import threading
from pathlib import Path


class LookupCache:
    """Group link -> chat id (None when Telegram rejected the link) and chat id -> title."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        data = self._read()
        self.links: dict[str, int | None] = dict(data.get("links", {}))
        self.titles: dict[str, str] = dict(data.get("titles", {}))

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def has_link(self, link: str) -> bool:
        return link in self.links

    def set_link(self, link: str, chat_id: int | None) -> None:
        self.links[link] = chat_id
        self.save()

    def title(self, chat_id: int) -> str | None:
        return self.titles.get(str(chat_id))

    def set_title(self, chat_id: int, title: str) -> None:
        self.titles[str(chat_id)] = title
        self.save()

    def save(self) -> None:
        """Write atomically (temp file + replace) so a crash never leaves a half-written cache."""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
            payload = {"links": self.links, "titles": self.titles}
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
            temporary.replace(self.path)
