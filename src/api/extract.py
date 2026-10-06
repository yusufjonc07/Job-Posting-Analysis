"""Turn raw Telegram message lines into dashboard rows using the project's own feature functions.

Every function here is top-level so a spawned ProcessPoolExecutor can pickle it; `init_worker`
loads the group locations once per worker process.
"""

import json
import re
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from config.settings import PROJECT_ROOT
from src.preprocess import CYRILLIC_PATTERN, HANGUL_PATTERN, LETTER_PATTERN
from src.utils.deduplication import dedup_key
from src.utils.job_filter import classify_post
from src.utils.locations import load_group_locations, resolve_location
from src.utils.post_parsing import parse_post
from src.utils.salary import main_salary
from src.utils.text_cleaning import EMAIL_PATTERN, MENTION_PATTERN, PHONE_PATTERN, URL_PATTERN, clean_text

GROUPS_CSV = PROJECT_ROOT / "data" / "telegram_groups.csv"

# Same terms as the analysis notebook; an ad names an occupation when one of its words fully matches.
OCCUPATIONS: dict[str, str] = {
    "Factory": r"zavod\w*|fabrika\w*|factory|공장\w*|생산\w*",
    "Kitchen / restaurant": r"oshxona\w*|restoran\w*|povar\w*|ofitsiant\w*|식당\w*|주방\w*",
    "Ships / fishing": r"kemasozlik\w*|kema(?:da|ga|ni|lar\w*)?|baliq\w*|조선\w*|어선\w*",
    "Cleaning": r"tozalash\w*|uborka\w*|청소\w*",
    "Construction": r"qurilish\w*|stroyk\w*|건설\w*|노가다",
    "Warehouse / logistics": r"ombor\w*|sklad\w*|물류\w*|창고\w*|택배\w*",
    "Agriculture": r"dala|dalada|ferma\w*|teplits\w*|issiqxona\w*|농장\w*|농사\w*",
    "Delivery": r"dostavk\w*|kuryer\w*|배달\w*|쿠팡",
}
OCCUPATION_NAMES = tuple(OCCUPATIONS)
OCCUPATION_PATTERNS = tuple(re.compile(pattern) for pattern in OCCUPATIONS.values())
ANY_OCCUPATION_PATTERN = re.compile("|".join(f"(?:{pattern})" for pattern in OCCUPATIONS.values()))
WORD_PATTERN = re.compile(r"(?u)\b\w\w+\b")

VISA_LOOKALIKES = str.maketrans("ЕеНнФфДд", "EeHhFfDd")
VISA_PATTERN = re.compile(r"(?<!\w)([EHFD])[- ]?(10|[2-9])(?!\d)", re.IGNORECASE)
VISA_TYPES = ("E-9", "E-7", "E-8", "H-2", "F-2", "F-4", "F-5", "F-6", "D-2", "D-4", "D-10")
VISA_BITS = {name: 1 << index for index, name in enumerate(VISA_TYPES)}

EXCERPT_LENGTH = 280
WHITESPACE = re.compile(r"\s+")

COLUMNS = (
    "row_id", "source_file", "msg_id", "line_no", "date", "dedup_key", "is_forwarded", "is_filled",
    "group_name", "province", "city", "location_source", "salary_krw", "salary_period", "has_phone",
    "has_url", "n_chars", "hangul_ratio", "cyrillic_ratio", "script", "occupations", "visas", "excerpt", "kind",
)

_group_locations: dict[int, tuple[str, str]] | None = None


def init_worker(groups_csv: str = str(GROUPS_CSV)) -> None:
    """Process-pool initializer: read telegram_groups.csv once per worker."""
    global _group_locations
    _group_locations = load_group_locations(Path(groups_csv))


def group_locations() -> dict[int, tuple[str, str]]:
    if _group_locations is None:
        init_worker()
    return _group_locations


@lru_cache(maxsize=200_000)
def token_occupations(token: str) -> int:
    """Bit mask of the occupations whose pattern fully matches one lower-case word."""
    if not ANY_OCCUPATION_PATTERN.match(token):
        return 0
    return sum(1 << index for index, pattern in enumerate(OCCUPATION_PATTERNS) if pattern.fullmatch(token))


def occupation_mask(body: str) -> int:
    words = set(WORD_PATTERN.findall(clean_text(body, mask_numbers=True).lower()))
    mask = 0
    for word in words:
        mask |= token_occupations(word)
    return mask


def visa_mask(body: str) -> int:
    found = {f"{letter.upper()}-{number}" for letter, number in VISA_PATTERN.findall(body.translate(VISA_LOOKALIKES))}
    return sum(VISA_BITS[name] for name in found if name in VISA_BITS)


def decode_mask(mask: int, names: tuple[str, ...]) -> list[str]:
    return [name for index, name in enumerate(names) if mask >> index & 1]


def excerpt(body: str) -> str:
    """Display text with contacts masked; the header (and its author) is never part of the body."""
    text = URL_PATTERN.sub("[link]", body)
    text = EMAIL_PATTERN.sub("[email]", text)
    text = MENTION_PATTERN.sub("@•••", text)
    text = PHONE_PATTERN.sub("☎ •••", text)
    text = WHITESPACE.sub(" ", text).strip()
    return text if len(text) <= EXCERPT_LENGTH else text[: EXCERPT_LENGTH - 1].rstrip() + "…"


def script_of(hangul_ratio: float, cyrillic_ratio: float) -> str:
    if hangul_ratio >= 0.5:
        return "Hangul"
    return "Cyrillic" if cyrillic_ratio >= 0.5 else "Latin"


def parse_date(value) -> int | None:
    """Epoch seconds from an ISO string ("2026-10-03 09:30:17+00:00") or an epoch number."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        moment = datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None
    return int((moment if moment.tzinfo else moment.replace(tzinfo=UTC)).timestamp())


def post_features(text: str, source_file: str, locations: dict[int, tuple[str, str]]) -> dict:
    """Every dashboard feature of one post with text."""
    post = parse_post(text)
    body = post["body"]
    province, city, location_source = resolve_location(text, source_file, locations)
    salary = main_salary(body)
    letters = max(len(LETTER_PATTERN.findall(body)), 1)
    hangul_ratio = len(HANGUL_PATTERN.findall(body)) / letters
    cyrillic_ratio = len(CYRILLIC_PATTERN.findall(body)) / letters
    return {
        "dedup_key": dedup_key(text),
        "is_forwarded": post["author"] is not None,
        "is_filled": post["is_filled"],
        "group_name": post["group_name"],
        "province": province,
        "city": city,
        "location_source": location_source,
        "salary_krw": float(salary.amount_krw) if salary else None,
        "salary_period": salary.period if salary else None,
        "has_phone": bool(PHONE_PATTERN.search(body)),
        "has_url": bool(URL_PATTERN.search(body)),
        "n_chars": len(body),
        "hangul_ratio": hangul_ratio,
        "cyrillic_ratio": cyrillic_ratio,
        "script": script_of(hangul_ratio, cyrillic_ratio),
        "occupations": occupation_mask(body),
        "visas": visa_mask(body),
        "excerpt": excerpt(body),
        "kind": classify_post(text),
    }


def extract_lines(source_file: str, lines: list[bytes], first_line_no: int = 1) -> dict[str, list]:
    """Columnar rows for complete JSONL lines; blank, broken and text-less messages are skipped."""
    locations = group_locations()
    columns: dict[str, list] = {name: [] for name in COLUMNS}
    for offset, raw in enumerate(lines):
        line_no = first_line_no + offset
        try:
            message = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(message, dict):
            continue
        text = message.get("message")
        text = text if isinstance(text, str) else ""
        if not text.strip():
            continue
        msg_id = message.get("id")
        msg_id = msg_id if isinstance(msg_id, int) and not isinstance(msg_id, bool) else None
        row = {
            "row_id": f"{source_file}:{msg_id}" if msg_id is not None else f"{source_file}#L{line_no}",
            "source_file": source_file,
            "msg_id": msg_id,
            "line_no": line_no,
            "date": parse_date(message.get("date")),
            **post_features(text, source_file, locations),
        }
        for name in COLUMNS:
            columns[name].append(row[name])
    return columns


def extract_range(path: str, start: int, end: int, first_line_no: int) -> dict[str, list]:
    """Worker entry point: extract the newline-terminated lines in bytes [start, end) of one file."""
    with open(path, "rb") as source:
        source.seek(start)
        data = source.read(end - start)
    return extract_lines(Path(path).name, data.split(b"\n")[:-1], first_line_no)
