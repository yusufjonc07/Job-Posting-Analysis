"""Application entry point for the Telegram job crawler."""

import sys
import time
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from src.crawler.messages import (
    extract_referenced_group_link,
    extract_referenced_group_name,
    group_filename,
    normalize_message,
)
from src.storage.jsonl import append_message_jsonl, load_checkpoint, save_checkpoint
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
        source_group_ids = (
            (settings.source_group_id,)
            if settings.source_group_id is not None
            else tuple(client.iter_group_ids_by_title(settings.source_group_title))
        )
        if not source_group_ids:
            raise ValueError(f"Source group not found: {settings.source_group_title!r}")

        for group_id in source_group_ids:
            group_title = str(group_id)
            try:
                group_title = client.get_group_title(group_id)
                print(f"\nCrawling source group: {group_title} ({group_id})")
                checkpoint_path = settings.raw_data_dir / ".state" / f"source_{group_id}.json"
                saved_id = load_checkpoint(checkpoint_path)
                monthly_counts: dict[str, int] = defaultdict(int)
                routed_counts: dict[str, int] = defaultdict(int)

                count = 0
                for message in client.iter_messages(group_id, min_id=saved_id):
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

                    raw_message = json.loads(normalized.raw_message_json)
                    referenced_group = extract_referenced_group_name(normalized.text)
                    referenced_link = extract_referenced_group_link(raw_message)
                    referenced_group_id = client.resolve_group_link(referenced_link)
                    if referenced_group_id is None:
                        output_path = settings.raw_data_dir / f"group_unmatched_{group_filename(referenced_group or 'unknown')}.jsonl"
                    else:
                        output_path = settings.raw_data_dir / f"group_{referenced_group_id}.jsonl"
                    append_message_jsonl(output_path, normalized)
                    save_checkpoint(checkpoint_path, normalized.message_id)
                    routed_counts[str(referenced_group_id or referenced_group or "unmatched")] += 1
                    count += 1

                month_summary = ", ".join(f"{month}: {amount}" for month, amount in monthly_counts.items())
                routing_summary = ", ".join(f"{name}: {amount}" for name, amount in routed_counts.items())
                print(f"Saved {count} new source messages from {group_title}")
                if month_summary:
                    print(f"  Monthly totals: {month_summary}")
                if routing_summary:
                    print(f"  Routed groups: {routing_summary}")
                if settings.request_delay_seconds > 0:
                    time.sleep(settings.request_delay_seconds)
            except Exception as error:
                print(f"ERROR while crawling {group_title} ({group_id}): {error}", file=sys.stderr)
                raise
    finally:
        client.close()


if __name__ == "__main__":
    main()
