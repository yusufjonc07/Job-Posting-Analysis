"""Find new job groups from the Telegram links mentioned in posts, and follow the ones with job offers.

    python -m src.discover_groups            # check up to 50 links, most mentioned first
    python -m src.discover_groups --list     # only list the candidate links (no Telegram request)

Every t.me link in data/raw (message text and link entities) is collected. For each public group or
channel that is not followed yet, its last 100 messages are read (one request) and classified with
src.utils.job_filter. A group with at least --min-jobs job offers, active in the last 30 days, is added
to data/telegram_groups.csv (province and city left empty, to be assigned later) and its checked
messages are saved to data/raw, so the listener follows it from then on without asking Telegram again.

Each link is checked once: results are kept in data/raw/.state/discovery.json (rejected links are checked
again after 30 days). Telegram limits username lookups, so a run stops at a long flood wait and the next
run continues where it stopped. When the listener is running it holds the Telegram session, so this
command asks the listener to run the check instead.
"""

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon.errors import FloodWaitError, RPCError

from config.settings import PROJECT_ROOT, settings
from src.crawler.listen import known_group_ids
from src.crawler.messages import normalize_message
from src.storage.jsonl import append_message_jsonl
from src.utils.job_filter import is_job_post

CHECK_MESSAGES = 100
MIN_JOBS = 5
MIN_MENTIONS = 2
MAX_AGE_DAYS = 30
RECHECK_DAYS = 30
RUN_LIMIT = 50
DISCOVER_EVERY_HOURS = float(os.getenv("DISCOVER_EVERY_HOURS", "24") or 0)  # the listener's automatic run; 0 = off
PAUSE_BETWEEN_CHECKS = 2.0
STATE_FILE = "discovery.json"
REQUEST_FILE = "discover.request"
GROUPS_CSV = PROJECT_ROOT / "data" / "telegram_groups.csv"
CSV_FIELDS = ["group_id", "group_title", "message_count", "last_msg_date", "province", "city"]

LINK = re.compile(r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/([A-Za-z0-9_+/\-]+)", re.IGNORECASE)
NOT_CHATS = {"share", "addstickers", "addemoji", "addlist", "proxy", "socks", "iv", "setlanguage", "addtheme", "login", "boost", "m", "contact"}


@dataclass(frozen=True)
class Options:
    limit: int = RUN_LIMIT
    min_jobs: int = MIN_JOBS
    min_mentions: int = MIN_MENTIONS
    dry_run: bool = False


def link_target(url: str) -> str | None:
    """'username:<name>' or 'id:<-100…>' for a link to a chat; None for invites, bots and other links."""
    match = LINK.search(url)
    if not match:
        return None
    parts = [part for part in match.group(1).split("/") if part]
    if not parts or parts[0].startswith("+") or parts[0].lower() == "joinchat":
        return None  # private invite: cannot be read without joining
    if parts[0].lower() == "c":
        return f"id:-100{parts[1]}" if len(parts) > 1 and parts[1].isdigit() else None
    if parts[0].lower() == "s" and len(parts) > 1:
        parts = parts[1:]  # t.me/s/<name> is a public preview of <name>
    name = parts[0].lower()
    if name in NOT_CHATS or name.endswith("bot") or not re.fullmatch(r"[a-z][a-z0-9_]{3,31}", name):
        return None
    return f"username:{name}"


def collect_links(raw_dir: Path) -> tuple[Counter, int]:
    """How often each chat link is mentioned in data/raw, and how many private invite links were seen."""
    targets: Counter = Counter()
    invites = 0
    for path in raw_dir.glob("group_*.jsonl"):
        with path.open(encoding="utf-8") as source:
            for line in source:
                if "t.me" not in line and "telegram.me" not in line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                urls = [str(message.get("message") or "")]
                urls += [str(e.get("url") or "") for e in message.get("entities") or [] if isinstance(e, dict)]
                for text in urls:
                    for match in LINK.finditer(text):
                        target = link_target(match.group(0))
                        if target:
                            targets[target] += 1
                        elif match.group(1).startswith("+") or match.group(1).lower().startswith("joinchat"):
                            invites += 1
    return targets, invites


def message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    return str((content.get("text") or {}).get("text") or "")


class DiscoveryState:
    """What was found for each link, kept on disk so a link is checked only once."""

    def __init__(self, path: Path):
        self.path = path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        self.checked: dict[str, dict] = data.get("checked", {})
        self.paused_until: float = float(data.get("paused_until", 0))
        self.last_run: float = float(data.get("last_run", 0))

    def due(self, target: str, now: float) -> bool:
        entry = self.checked.get(target)
        if entry is None:
            return True
        return not entry.get("added") and entry.get("result") in {"rejected", "error"} and now - entry.get("checked_at", 0) > RECHECK_DAYS * 86_400

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        payload = {"checked": self.checked, "paused_until": self.paused_until, "last_run": self.last_run}
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)


def add_group_row(groups_csv: Path, group_id: int, title: str, message_count: int, last_date: str) -> None:
    """Append the group to telegram_groups.csv; province and city stay empty until assigned."""
    new_file = not groups_csv.is_file()
    if not new_file and not groups_csv.read_bytes().endswith(b"\n"):
        with groups_csv.open("a", encoding="utf-8") as target:
            target.write("\n")
    with groups_csv.open("a", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=CSV_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow({"group_id": group_id, "group_title": title, "message_count": message_count,
                         "last_msg_date": last_date, "province": "", "city": ""})


async def discover(
    client: Any,
    raw_dir: Path,
    groups_csv: Path = GROUPS_CSV,
    options: Options = Options(),
    log: Callable[[str], None] = print,
) -> list[dict]:
    """Check the most mentioned links that are not followed yet; returns the groups added."""
    state = DiscoveryState(raw_dir / ".state" / STATE_FILE)
    now = time.time()
    if state.paused_until > now:
        log(f"Telegram asked to wait; group discovery continues after {datetime.fromtimestamp(state.paused_until):%Y-%m-%d %H:%M}")
        return []
    followed = set(known_group_ids(raw_dir, groups_csv))
    targets, invites = await asyncio.to_thread(collect_links, raw_dir)
    queue = [t for t, n in targets.most_common() if n >= options.min_mentions and state.due(t, now)]
    log(f"Group discovery: {len(targets):,} linked chats ({invites:,} private invite links skipped), "
        f"{len(queue):,} not checked yet; checking up to {options.limit}")
    added: list[dict] = []
    checked = 0
    for target in queue:
        if checked >= options.limit:
            break
        entry: dict[str, Any] = {"mentions": targets[target], "checked_at": time.time()}
        try:
            info = await resolve(client, target)
            if info is None:
                entry["result"] = "not_a_group"
            elif info["id"] in followed:
                entry.update(info, result="already_followed")
            else:
                checked += 1
                entry.update(info)
                messages = [m async for m in client.iter_messages_async(info["id"], limit=CHECK_MESSAGES)]
                jobs = sum(is_job_post(message_text(m)) for m in messages)
                newest = max((m.get("date") or 0 for m in messages), default=0)
                active = newest >= time.time() - MAX_AGE_DAYS * 86_400
                entry.update(messages=len(messages), jobs=jobs, newest=newest)
                if jobs >= options.min_jobs and active:
                    entry["result"] = "added"
                    if not options.dry_run:
                        save_history(raw_dir, info["id"], messages)
                        last = datetime.fromtimestamp(newest, UTC).isoformat(sep=" ") if newest else ""
                        add_group_row(groups_csv, info["id"], info["title"], len(messages), last)
                        followed.add(info["id"])
                        entry["added"] = True
                    added.append(entry)
                    log(f"  + {info['title']} ({info['id']}): {jobs} job offers in the last {len(messages)} messages"
                        f"{' (dry run, not added)' if options.dry_run else ' -> now followed'}")
                else:
                    entry["result"] = "rejected"
                    reason = "inactive for 30+ days" if not active else f"{jobs} job offers in the last {len(messages)} messages"
                    log(f"  - {info['title']} ({info['id']}): {reason}")
                await asyncio.sleep(PAUSE_BETWEEN_CHECKS)
        except FloodWaitError as error:
            state.paused_until = time.time() + error.seconds
            state.save()
            log(f"Telegram asked to wait {error.seconds} s; group discovery stops here and continues later")
            break
        except (ValueError, TypeError, RPCError) as error:  # unknown username, private chat, ...
            entry.update(result="error", error=f"{type(error).__name__}: {error}")
        state.checked[target] = entry
        state.save()
    state.last_run = time.time()
    state.save()
    log(f"Group discovery done: {len(added)} group(s) {'would be ' if options.dry_run else ''}added")
    return added


async def resolve(client: Any, target: str) -> dict | None:
    kind, value = target.split(":", 1)
    if kind == "id":
        chat_id = int(value)
        if not await client.can_read_async(chat_id):
            raise ValueError("private chat the account is not in")
        return {"id": chat_id, "title": await client.get_group_title_async(chat_id), "kind": "group"}
    return await client.resolve_username_async(value)


def save_history(raw_dir: Path, group_id: int, messages: list[dict[str, Any]]) -> None:
    """The checked messages become the group's history (oldest first), so they are not requested again."""
    path = raw_dir / f"group_{group_id}.jsonl"
    for message in sorted(messages, key=lambda m: int(m.get("id", 0))):
        append_message_jsonl(path, normalize_message({**message, "chat_id": group_id}))


def request_path(raw_dir: Path) -> Path:
    return raw_dir / ".state" / REQUEST_FILE


def read_request(raw_dir: Path) -> Options | None:
    """Options of a discovery the command line asked the running listener to do (and clears the request)."""
    path = request_path(raw_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    path.unlink(missing_ok=True)
    return Options(**{key: data[key] for key in ("limit", "min_jobs", "min_mentions", "dry_run") if key in data})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m src.discover_groups", description=__doc__.split("\n\n")[0])
    parser.add_argument("--limit", type=int, default=RUN_LIMIT, help=f"chats to check in this run (default {RUN_LIMIT})")
    parser.add_argument("--min-jobs", type=int, default=MIN_JOBS, help=f"job offers needed in the last {CHECK_MESSAGES} messages (default {MIN_JOBS})")
    parser.add_argument("--min-mentions", type=int, default=MIN_MENTIONS, help=f"skip links mentioned fewer times (default {MIN_MENTIONS})")
    parser.add_argument("--dry-run", action="store_true", help="check, but do not add any group")
    parser.add_argument("--list", action="store_true", help="only list candidate links, without asking Telegram")
    return parser.parse_args(argv)


async def run_standalone(options: Options) -> int:
    from src.main import EXIT_NOT_LOGGED_IN, new_client

    client = new_client()
    try:
        if not await client.connect_authorized_async():
            print("Not logged in to Telegram. Run `python -m src.main` once to log in.", file=sys.stderr)
            return EXIT_NOT_LOGGED_IN
        await discover(client, settings.raw_data_dir, GROUPS_CSV, options)
        return 0
    finally:
        await client.close_async()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    options = Options(limit=args.limit, min_jobs=args.min_jobs, min_mentions=args.min_mentions, dry_run=args.dry_run)
    raw_dir = settings.raw_data_dir
    if args.list:
        targets, invites = collect_links(raw_dir)
        state = DiscoveryState(raw_dir / ".state" / STATE_FILE)
        now = time.time()
        due = [(t, n) for t, n in targets.most_common() if n >= options.min_mentions and state.due(t, now)]
        print(f"{len(targets):,} linked chats, {invites:,} private invite links; {len(due):,} to check (mentioned {options.min_mentions}+ times):")
        for target, count in due[:100]:
            print(f"  {count:6,}  {target}")
        return

    from src.main import acquire_session_lock

    lock = acquire_session_lock()
    if lock is None:  # the listener holds the session: let it do the check
        path = request_path(raw_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(options.__dict__), encoding="utf-8")
        print("The listener is running and holds the Telegram session; it will run the check within a minute.\n"
              "Watch the server log for the results ([telegram] lines starting with 'Group discovery').")
        return
    try:
        code = asyncio.run(run_standalone(options))
    finally:
        lock.close()
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
