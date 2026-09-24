"""Application entry point for the Telegram job crawler."""

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from src.storage.txt import ensure_raw_directory


def main() -> None:
    """Prepare the crawler workspace and report the active configuration."""
    ensure_raw_directory(settings.raw_data_dir)
    print(f"Telegram job crawler ready. Raw data: {settings.raw_data_dir}")
    if settings.telegram_group_ids:
        print(f"Configured groups: {len(settings.telegram_group_ids)}")
    else:
        print("Group selection: all joined groups")


if __name__ == "__main__":
    main()
