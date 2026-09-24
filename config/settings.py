"""Environment-backed application settings."""

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(_: Path) -> bool:
        """Allow environment-only configuration before dependencies are installed."""
        return False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    telegram_api_id: int
    telegram_api_hash: str
    telegram_phone_number: str
    telegram_group_ids: tuple[int, ...]
    tdlib_database_dir: Path
    raw_data_dir: Path


def _group_ids(value: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in value.split(",") if item.strip())


def _settings() -> Settings:
    return Settings(
        telegram_api_id=int(os.getenv("TELEGRAM_API_ID", "0")),
        telegram_api_hash=os.getenv("TELEGRAM_API_HASH", ""),
        telegram_phone_number=os.getenv("TELEGRAM_PHONE_NUMBER", ""),
        telegram_group_ids=_group_ids(os.getenv("TELEGRAM_GROUP_IDS", "")),
        tdlib_database_dir=Path(os.getenv("TDLIB_DATABASE_DIR", str(PROJECT_ROOT / "data" / "tdlib"))),
        raw_data_dir=Path(os.getenv("RAW_DATA_DIR", str(PROJECT_ROOT / "data" / "raw"))),
    )


settings = _settings()
