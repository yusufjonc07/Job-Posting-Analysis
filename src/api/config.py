"""Paths and environment settings for the dashboard API."""

import os
from dataclasses import dataclass
from pathlib import Path

from config.settings import PROJECT_ROOT  # importing settings also loads .env

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


@dataclass(frozen=True)
class ApiConfig:
    """Everything the store and the app need; tests build one directly."""

    raw_dir: Path
    cache_dir: Path
    groups_csv: Path = PROJECT_ROOT / "data" / "telegram_groups.csv"
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"
    poll_seconds: float = 2.0
    cors_origins: tuple[str, ...] = tuple(DEFAULT_CORS_ORIGINS.split(","))
    workers: int = max((os.cpu_count() or 2) - 1, 1)
    save_interval: float = 60.0
    use_cache: bool = True


def resolve_path(value: str | None, default: Path) -> Path:
    """Expand a path from the environment; relative paths are taken from the project root."""
    if not value or not value.strip():
        return default
    path = Path(value.strip()).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_config() -> ApiConfig:
    """Read the API_* variables (and RAW_DATA_DIR) from the environment."""
    origins = os.getenv("API_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    workers = os.getenv("API_WORKERS", "").strip()
    return ApiConfig(
        raw_dir=resolve_path(os.getenv("RAW_DATA_DIR"), PROJECT_ROOT / "data" / "raw"),
        cache_dir=resolve_path(os.getenv("API_CACHE_DIR"), PROJECT_ROOT / "data" / "cache"),
        poll_seconds=float(os.getenv("API_POLL_SECONDS", "2") or 2),
        cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
        workers=max(int(workers), 1) if workers else max((os.cpu_count() or 2) - 1, 1),
    )
