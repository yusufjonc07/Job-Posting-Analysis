"""Application entry point for the Telegram job crawler."""

import argparse
import sys
import time
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon.errors import BadRequestError

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

MIN_INTERVAL_SECONDS = 30

_unresolvable_links: set[str] = set()


def _interval_seconds(value: str) -> int:
    """Parse --every, refusing intervals short enough to strain Telegram."""
    try:
        seconds = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected whole seconds, got {value!r}") from None
    if seconds < MIN_INTERVAL_SECONDS:
        raise argparse.ArgumentTypeError(f"must be at least {MIN_INTERVAL_SECONDS} seconds, got {seconds}")
    return seconds


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line: one pass by default, or one pass every --every seconds."""
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="Crawl the Ish e'lonlari source group and append new messages to RAW_DATA_DIR.",
    )
    parser.add_argument(
        "--every",
        type=_interval_seconds,
        metavar="SECONDS",
        help=(
            "keep running: start another pass SECONDS after each pass ends "
            f"(at least {MIN_INTERVAL_SECONDS}); stop with Ctrl+C"
        ),
    )
    return parser.parse_args(argv)


def source_group_ids(client: TdlibClient) -> tuple[int, ...]:
    """Return the configured source group, or the joined groups matching its title."""
    group_ids = (
        (settings.source_group_id,)
        if settings.source_group_id is not None
        else tuple(client.iter_group_ids_by_title(settings.source_group_title))
    )
    if not group_ids:
        raise ValueError(f"Source group not found: {settings.source_group_title!r}")
    return group_ids


def resolve_destination(client: TdlibClient, link: str | None) -> int | None:
    """Resolve a Guruh link, routing links Telegram rejects to the unmatched files."""
    if not link or link in _unresolvable_links:
        return None
    try:
        return client.resolve_group_link(link)
    except (ValueError, BadRequestError) as error:
        _unresolvable_links.add(link)
        print(f"  Cannot resolve group link {link}: {error}", file=sys.stderr)
        return None


def crawl_group(client: TdlibClient, group_id: int) -> int:
    """Append the group's messages newer than its checkpoint and return how many were saved."""
    group_title = str(group_id)
    try:
        group_title = client.get_group_title(group_id)
        print(f"\nCrawling source group: {group_title} ({group_id})")
        checkpoint_path = settings.raw_data_dir / ".state" / f"source_{group_id}.json"
        saved_id = load_checkpoint(checkpoint_path)
        highest_id = saved_id
        monthly_counts: dict[str, int] = defaultdict(int)
        routed_counts: dict[str, int] = defaultdict(int)

        count = 0
        for message in client.iter_messages(group_id, min_id=saved_id):
            normalized = normalize_message(message)
            if normalized.message_id <= saved_id:
                continue
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
            referenced_group_id = resolve_destination(client, referenced_link)
            if referenced_group_id is None:
                output_path = settings.raw_data_dir / f"group_unmatched_{group_filename(referenced_group or 'unknown')}.jsonl"
            else:
                output_path = settings.raw_data_dir / f"group_{referenced_group_id}.jsonl"
            append_message_jsonl(output_path, normalized)
            highest_id = max(highest_id, normalized.message_id)
            routed_counts[str(referenced_group_id or referenced_group or "unmatched")] += 1
            count += 1

        if highest_id > load_checkpoint(checkpoint_path):
            save_checkpoint(checkpoint_path, highest_id)

        month_summary = ", ".join(f"{month}: {amount}" for month, amount in monthly_counts.items())
        routing_summary = ", ".join(f"{name}: {amount}" for name, amount in routed_counts.items())
        print(f"Saved {count} new source messages from {group_title}")
        if month_summary:
            print(f"  Monthly totals: {month_summary}")
        if routing_summary:
            print(f"  Routed groups: {routing_summary}")
        if settings.request_delay_seconds > 0:
            time.sleep(settings.request_delay_seconds)
        return count
    except Exception as error:
        print(f"ERROR while crawling {group_title} ({group_id}): {error}", file=sys.stderr)
        raise


def crawl_pass(client: TdlibClient, group_ids: tuple[int, ...]) -> int:
    """Crawl every source group once and return the number of saved messages."""
    return sum(crawl_group(client, group_id) for group_id in group_ids)


def _now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def crawl_forever(client: TdlibClient, every: int) -> None:
    """Run a pass every `every` seconds until Ctrl+C; a failed pass is logged and retried."""
    print(f"Crawling every {every} s; press Ctrl+C to stop.", flush=True)
    group_ids: tuple[int, ...] = ()
    passes = saved_total = 0
    try:
        while True:
            started = time.monotonic()
            try:
                group_ids = group_ids or source_group_ids(client)
                saved = crawl_pass(client, group_ids)
            except Exception as error:
                passes += 1
                print(
                    f"[{_now()}] Pass {passes} failed ({type(error).__name__}: {error}); retrying in {every} s",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                passes += 1
                saved_total += saved
                print(
                    f"[{_now()}] Pass {passes}: {saved} new messages in {time.monotonic() - started:.1f} s; "
                    f"next pass in {every} s",
                    flush=True,
                )
            time.sleep(every)
    except KeyboardInterrupt:
        print(f"\nStopped after {passes} passes; {saved_total} new messages saved in this run.", flush=True)


def main(argv: list[str] | None = None) -> None:
    """Authenticate, then crawl the source groups once, or every --every seconds until Ctrl+C."""
    args = parse_args(argv)
    ensure_raw_directory(settings.raw_data_dir)
    client = TdlibClient(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        phone_number=settings.telegram_phone_number,
        database_directory=settings.tdlib_database_dir,
    )
    client.start()
    try:
        if args.every is None:
            crawl_pass(client, source_group_ids(client))
        else:
            crawl_forever(client, args.every)
    finally:
        client.close()


if __name__ == "__main__":
    main()
