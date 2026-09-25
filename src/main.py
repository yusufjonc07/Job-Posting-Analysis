"""Application entry point for the Telegram job crawler."""

import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from src.crawler.messages import normalize_message
from src.storage.jsonl import append_messages_jsonl, last_message_id
from src.storage.txt import ensure_raw_directory
from src.tdlib.client import TdlibClient


def main() -> None:
    """Authenticate, crawl target groups, and save their messages."""
    ensure_raw_directory(settings.raw_data_dir)
    client = TdlibClient(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        phone_number=settings.telegram_phone_number,
        database_directory=settings.tdlib_database_dir,
    )
    client.start()
    try:
        group_ids = client.iter_target_group_ids(settings.telegram_group_ids)
        for group_id in group_ids:
            group_title = str(group_id)
            try:
                group_title = client.get_group_title(group_id)
                print(f"\nCrawling group: {group_title} ({group_id})")
                output_path = settings.raw_data_dir / f"group_{group_id}.jsonl"
                saved_id = last_message_id(output_path)
                monthly_counts: dict[str, int] = defaultdict(int)

                def new_messages():
                    for message in client.iter_messages(
                        group_id,
                        min_id=saved_id,
                    ):
                        normalized = normalize_message(message)
                        if (
                            settings.crawl_until_timestamp is not None
                            and normalized.date is not None
                            and normalized.date < settings.crawl_until_timestamp
                        ):
                            break
                        if normalized.date is not None:
                            month = datetime.fromtimestamp(normalized.date, tz=UTC).strftime("%Y-%m")
                            if month not in monthly_counts:
                                print(f"  Crawling month: {month}")
                            monthly_counts[month] += 1
                        yield normalized

                count = append_messages_jsonl(output_path, new_messages())
                month_summary = ", ".join(f"{month}: {amount}" for month, amount in monthly_counts.items())
                print(f"Saved {count} new messages for {group_title} to {output_path}")
                if month_summary:
                    print(f"  Monthly totals: {month_summary}")
                if settings.request_delay_seconds > 0:
                    time.sleep(settings.request_delay_seconds)
            except Exception as error:
                print(f"ERROR while crawling {group_title} ({group_id}): {error}", file=sys.stderr)
                raise
    finally:
        client.close()


if __name__ == "__main__":
    main()
