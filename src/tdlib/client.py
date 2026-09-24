"""Small boundary around a TDLib client implementation."""

from collections.abc import Iterator
from typing import Any


class TdlibClient:
    """Represent the connection used to receive Telegram updates.

    The TDLib binary and binding are deployment-specific, so this class keeps
    the rest of the crawler independent from that integration detail.
    """

    def __init__(self, api_id: int, api_hash: str, database_directory: str) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.database_directory = database_directory
        self._started = False

    def start(self) -> None:
        """Start the client connection."""
        self._started = True

    def iter_joined_group_ids(self) -> Iterator[int]:
        """Yield IDs for all groups and supergroups joined by the account."""
        if not self._started:
            raise RuntimeError("Start the TDLib client before listing groups")
        raise NotImplementedError("Connect this boundary to the chosen TDLib Python binding")

    def iter_target_group_ids(self, configured_ids: tuple[int, ...]) -> Iterator[int]:
        """Use configured groups, or discover every joined group when unset."""
        if configured_ids:
            yield from configured_ids
            return
        yield from self.iter_joined_group_ids()

    def iter_messages(self, chat_id: int, limit: int = 100) -> Iterator[dict[str, Any]]:
        """Yield messages for a chat once a concrete TDLib adapter is connected."""
        if not self._started:
            raise RuntimeError("Start the TDLib client before reading messages")
        if limit < 1:
            return
        raise NotImplementedError("Connect this boundary to the chosen TDLib Python binding")

    def close(self) -> None:
        """Close the client connection."""
        self._started = False
