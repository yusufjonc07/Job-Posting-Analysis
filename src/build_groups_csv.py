"""Rebuild data/telegram_groups.csv from the routed JSONL files in data/raw."""

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon.tl.types import PeerChannel

from config.settings import PROJECT_ROOT, settings
from src.crawler.messages import extract_referenced_group_link, extract_referenced_group_name
from src.tdlib.client import TdlibClient

OUTPUT_PATH = PROJECT_ROOT / "data" / "telegram_groups.csv"
FIELDS = ("group_id", "group_title", "message_count", "last_msg_date", "province", "city")

# (province, city) inferred from group titles; universities map to their campus location.
# Groups covering several areas use the first/main one; "Nationwide" means no single region.
GROUP_LOCATIONS: dict[int, tuple[str, str]] = {
    -1001548974049: ("Nationwide", ""),
    -1001857660612: ("Jeollanam-do", "Mokpo"),
    -1001742386027: ("Daegu", "Daegu"),
    -1001141152967: ("Gyeonggi-do", "Seongnam"),  # Gachon University
    -1002525696680: ("Gyeonggi-do", "Seongnam"),
    -1001212678634: ("Chungcheongnam-do", "Cheonan"),
    -1001176433500: ("Gyeongsangbuk-do", "Gyeongsan"),  # Yeungnam University
    -1002166549165: ("Seoul", "Seoul"),
    -1001544370991: ("Nationwide", ""),
    -1001247733613: ("Chungcheongbuk-do", "Cheongju"),
    -1001440276367: ("Gyeongsangnam-do", "Gimhae"),
    -1002643935758: ("Seoul", "Seoul"),
    -1001470356319: ("Gyeonggi-do", "Anseong"),
    -1001152680949: ("Nationwide", ""),
    -1001686180833: ("Gwangju", "Gwangju"),
    -1002858032342: ("Gyeonggi-do", "Yongin"),
    -1001511479567: ("Gyeonggi-do", "Icheon"),
    -1001506536751: ("Jeollabuk-do", "Gunsan"),
    -1002462126497: ("Gangwon-do", "Wonju"),
    -1002165832122: ("Chungcheongbuk-do", "Chungju"),
    -1001799111985: ("Chungcheongbuk-do", "Eumseong"),  # Daeso, Samseong, Geumwang; also Jincheon
    -1001670761222: ("Daejeon", "Daejeon"),
    -1001659856299: ("Nationwide", ""),
    -1001507058507: ("Gyeonggi-do", "Ansan"),
    -1001754360080: ("Jeollabuk-do", "Iksan"),
    -1002567337700: ("Ulsan", "Ulsan"),
    -1001716701670: ("Gyeonggi-do", "Pyeongtaek"),  # Poseung-eup
    -1002044373140: ("Gyeonggi-do", "Gimpo"),
    -1002603723162: ("Chungcheongnam-do", "Cheonan"),
    -1002628556472: ("Jeollanam-do", "Mokpo"),
    -1001503748476: ("Busan", "Busan"),
    -1001205456019: ("Daejeon", "Daejeon"),
    -1003031272657: ("Gyeonggi-do", "Gimpo"),
    -1002602937985: ("Gyeonggi-do", "Osan"),
    -1001387204774: ("Jeollabuk-do", "Gunsan"),
    -1001239333237: ("Seoul", "Seoul"),
    -1004332184742: ("Daejeon", "Daejeon"),
    -1002220341034: ("Daegu", "Daegu"),
    -1001617766928: ("Chungcheongnam-do", "Cheonan"),  # Seonghwan-eup
    -1001568438899: ("Gyeonggi-do", "Paju"),
    -1002729014093: ("Gyeonggi-do", "Suwon"),
    -1001671731305: ("Daegu", "Daegu"),
    -1002069815122: ("Gyeonggi-do", "Uijeongbu"),
    -1001510293511: ("Gyeongsangnam-do", "Yangsan"),
    -1002179593933: ("Chungcheongnam-do", "Cheonan"),
    -1002231609363: ("Gyeonggi-do", "Icheon"),
    -1001157420605: ("Gyeonggi-do", "Ansan"),
    -1001872468679: ("Chungcheongbuk-do", "Jecheon"),
    -1001161946122: ("Busan", "Busan"),
    -1002039556203: ("Gyeongsangnam-do", "Geoje"),
    -1002943976884: ("Chungcheongbuk-do", "Cheongju"),
    -1001749857007: ("Incheon", "Incheon"),
    -1002039673694: ("Jeollabuk-do", "Iksan"),
    -1001626809647: ("Seoul", "Seoul"),
    -1002927407248: ("Daejeon", "Daejeon"),
    -1001821504643: ("Chungcheongnam-do", "Dangjin"),
    -1001973154125: ("Gyeonggi-do", "Bucheon"),
    -1001225201479: ("Gyeonggi-do", "Ansan"),
    -1002551608059: ("Jeollanam-do", "Yeongam"),  # Daebul / Samho shipyard, near Mokpo
    -1002935311191: ("Busan", "Busan"),
    -1001146665528: ("Nationwide", ""),
    -1001463257290: ("Nationwide", ""),
    -1002075584771: ("Gyeongsangnam-do", "Geoje"),
    -1002318092771: ("Gyeonggi-do", "Yangju"),
    -1002045737688: ("Incheon", "Incheon"),  # posts are about Incheon
    -1001758907421: ("Incheon", "Incheon"),
    -1001381770202: ("Daegu", "Daegu"),
    -1001304686518: ("Nationwide", ""),
    -1002126377487: ("Nationwide", ""),
    -1002553359624: ("Nationwide", ""),
}


def channel_id(file_id: int) -> int:
    """Normalize a bare channel ID (from username resolution) to the -100 form."""
    return file_id if file_id < 0 else int(f"-100{file_id}")


def scan_raw_files(raw_dir: Path) -> dict[int, dict]:
    """Collect message counts, last dates, and referenced names/links per group."""
    groups: dict[int, dict] = defaultdict(
        lambda: {"message_count": 0, "last_msg_date": "", "names": set(), "links": set(), "raw_ids": set()}
    )
    for path in sorted(raw_dir.glob("group_*.jsonl")):
        match = re.fullmatch(r"group_(-?\d+)\.jsonl", path.name)
        if not match:
            print(f"Skipping unmatched file: {path.name}")
            continue
        raw_id = int(match.group(1))
        group = groups[channel_id(raw_id)]
        group["raw_ids"].add(raw_id)
        with path.open(encoding="utf-8") as source:
            for line in source:
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                group["message_count"] += 1
                date = str(message.get("date") or "")
                group["last_msg_date"] = max(group["last_msg_date"], date)
                if name := extract_referenced_group_name(str(message.get("message", ""))):
                    group["names"].add(name)
                if link := extract_referenced_group_link(message):
                    group["links"].add(link)
    return groups


def fetch_title(client: TdlibClient, group_id: int, raw_ids: set[int], links: set[str]) -> str | None:
    """Look up a group title by ID, falling back to the links seen in its messages."""
    candidates: list = [PeerChannel(int(str(group_id).removeprefix("-100")))]
    candidates += [raw_id for raw_id in raw_ids if raw_id > 0]
    for candidate in candidates:
        try:
            entity = client._client.get_entity(candidate)
            return getattr(entity, "title", None) or getattr(entity, "first_name", None)
        except (ValueError, TypeError):
            continue
        except Exception as error:
            print(f"  {group_id}: lookup failed ({error})", file=sys.stderr)
    for link in links:
        username = re.search(r"(?:t\.me|telegram\.me)/([A-Za-z0-9_]+)", link)
        if not username or username.group(1) in {"c", "joinchat"}:
            continue
        try:
            entity = client._client.get_entity(username.group(1))
            return getattr(entity, "title", None) or getattr(entity, "first_name", None)
        except Exception as error:
            print(f"  {group_id}: link {link} failed ({error})", file=sys.stderr)
    return None


def main() -> None:
    groups = scan_raw_files(settings.raw_data_dir)
    client = TdlibClient(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        phone_number=settings.telegram_phone_number,
        database_directory=settings.tdlib_database_dir,
    )
    client.start()
    rows = []
    try:
        for group_id, group in groups.items():
            title = fetch_title(client, group_id, group["raw_ids"], group["links"])
            if title is None:
                title = sorted(group["names"])[0] if group["names"] else ""
                print(f"  {group_id}: not resolvable, using name from posts: {title!r}")
            rows.append({
                "group_id": group_id,
                "group_title": title,
                "message_count": group["message_count"],
                "last_msg_date": group["last_msg_date"],
            })
    finally:
        client.close()

    if OUTPUT_PATH.exists():
        with OUTPUT_PATH.open(encoding="utf-8") as existing:
            rows += [row for row in csv.DictReader(existing) if int(row["group_id"]) not in groups]

    for row in rows:
        row["province"], row["city"] = GROUP_LOCATIONS.get(int(row["group_id"]), ("", ""))

    rows.sort(key=lambda row: int(row["message_count"]), reverse=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} groups to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
