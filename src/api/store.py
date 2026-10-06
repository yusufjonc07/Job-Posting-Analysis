"""In-memory store of extracted rows that follows data/raw as the crawler appends to it.

Only the ingest thread changes the store. Readers take `store.snapshot`, an immutable bundle of
DataFrames that is swapped as a whole after every change, so a frame a reader holds never changes.
"""

import csv
import hashlib
import logging
import os
import pickle
import threading
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import PROJECT_ROOT
from src.api import extract
from src.api.config import ApiConfig
from src.utils.locations import group_id_from_source

log = logging.getLogger("src.api.store")

SCHEMA_VERSION = 1
CACHE_FILE = "snapshot.pkl"
CHUNK_BYTES = 1 << 20          # about 2,500 lines per process-pool task
POOL_MIN_BYTES = 4 << 20       # a catch-up larger than this uses the process pool
TAIL_BYTES = 64                # bytes before the read offset, to notice a rewritten file
STATUS_INTERVAL = 1.0
KST_OFFSET_SECONDS = 9 * 3600

PROVINCE_IDS = (
    "Seoul", "Busan", "Daegu", "Incheon", "Gwangju", "Daejeon", "Ulsan", "Sejong", "Gyeonggi-do",
    "Gangwon-do", "Chungcheongbuk-do", "Chungcheongnam-do", "Jeollabuk-do", "Jeollanam-do",
    "Gyeongsangbuk-do", "Gyeongsangnam-do", "Jeju-do",
)
LOCATION_SOURCES = ("address", "text", "group", "unknown")
PERIODS = ("hourly", "daily", "monthly")
SCRIPTS = ("Latin", "Cyrillic", "Hangul")
CACHE_INPUTS = (
    "src/api/extract.py", "src/preprocess.py", "src/utils/deduplication.py", "src/utils/locations.py",
    "src/utils/post_parsing.py", "src/utils/salary.py", "src/utils/text_cleaning.py",
    "src/utils/transliteration.py",
)


@dataclass
class FileState:
    inode: int
    size: int
    offset: int = 0      # bytes consumed, always just after a newline
    lines: int = 0       # complete lines consumed
    tail: bytes = b""    # the TAIL_BYTES before `offset`


@dataclass(frozen=True)
class Snapshot:
    version: int
    posts: pd.DataFrame          # every post with text, reposts included
    ads: pd.DataFrame            # one representative row per unique ad, oldest first
    groups: pd.DataFrame         # per source_file: group_id, title, home_province, home_city
    files: int
    last_update: datetime | None
    last_post: datetime | None


@dataclass
class Batch:
    """Lines read in one pass: new rows plus the files whose old rows must be dropped first."""

    frames: list[pd.DataFrame] = field(default_factory=list)
    reset_files: set[str] = field(default_factory=set)
    removed_files: set[str] = field(default_factory=set)


def empty_rows() -> pd.DataFrame:
    return rows_frame({name: [] for name in extract.COLUMNS})


def rows_frame(columns: dict[str, list]) -> pd.DataFrame:
    """Typed DataFrame from the extractor's columnar output."""
    frame = pd.DataFrame({
        "row_id": pd.Series(columns["row_id"], dtype=object),
        "source_file": pd.Series(columns["source_file"], dtype=object),
        "msg_id": pd.array(columns["msg_id"], dtype="Int64"),
        "line_no": np.asarray(columns["line_no"], dtype=np.int64),
        "date": pd.to_datetime(pd.Series(columns["date"], dtype="float64"), unit="s", utc=True),
        "dedup_key": pd.Series(columns["dedup_key"], dtype=object),
        "is_forwarded": np.asarray(columns["is_forwarded"], dtype=bool),
        "is_filled": np.asarray(columns["is_filled"], dtype=bool),
        "group_name": pd.Series(columns["group_name"], dtype=object),
        "province": pd.Series(columns["province"], dtype=object),
        "city": pd.Series(columns["city"], dtype=object),
        "location_source": pd.Categorical(columns["location_source"], categories=LOCATION_SOURCES),
        "salary_krw": pd.Series(columns["salary_krw"], dtype="float64"),
        "salary_period": pd.Categorical(columns["salary_period"], categories=PERIODS),
        "has_phone": np.asarray(columns["has_phone"], dtype=bool),
        "has_url": np.asarray(columns["has_url"], dtype=bool),
        "n_chars": np.asarray(columns["n_chars"], dtype=np.int64),
        "hangul_ratio": np.asarray(columns["hangul_ratio"], dtype=np.float32),
        "cyrillic_ratio": np.asarray(columns["cyrillic_ratio"], dtype=np.float32),
        "script": pd.Categorical(columns["script"], categories=SCRIPTS),
        "occupations": np.asarray(columns["occupations"], dtype=np.int32),
        "visas": np.asarray(columns["visas"], dtype=np.int32),
        "excerpt": pd.Series(columns["excerpt"], dtype=object),
    })
    return frame


def concat_rows(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [frame for frame in frames if len(frame)]
    if not frames:
        return empty_rows()
    return frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)


def with_derived(posts: pd.DataFrame) -> pd.DataFrame:
    """Columns the aggregations use on every request: Korea-time day and map region."""
    seconds = posts["date"].to_numpy("datetime64[s]").astype(np.int64)
    valid = posts["date"].notna().to_numpy()
    kst_day = np.where(valid, (seconds + KST_OFFSET_SECONDS) // 86_400, np.iinfo(np.int32).min)
    province = posts["province"]
    on_map = province.isin(PROVINCE_IDS).to_numpy()
    from_post = posts["location_source"].isin(("address", "text")).to_numpy()
    return posts.assign(
        kst_day=kst_day.astype(np.int32),
        region=pd.Categorical(province.where(on_map), categories=PROVINCE_IDS),
        region_post=pd.Categorical(province.where(on_map & from_post), categories=PROVINCE_IDS),
    )


def unique_ads(posts: pd.DataFrame) -> pd.DataFrame:
    """Earliest copy of each ad by (date, row id) plus repost_count; empty keys are their own ad."""
    if posts.empty:
        return posts.assign(repost_count=pd.Series(dtype=np.int64))
    dates = posts["date"].to_numpy("datetime64[ns]").astype(np.int64)
    dates = np.where(posts["date"].notna().to_numpy(), dates, np.iinfo(np.int64).max)
    files = pd.factorize(posts["source_file"], sort=True)[0]
    msg_ids = posts["msg_id"].fillna(-1).to_numpy(np.int64)
    order = np.lexsort((posts["line_no"].to_numpy(), msg_ids, files, dates))
    keys = posts["dedup_key"].to_numpy()[order]
    has_key = keys != ""
    repeated = pd.Series(keys).duplicated().to_numpy() & has_key
    representatives = order[~repeated]
    counts = posts["dedup_key"].value_counts()
    ads = posts.iloc[representatives]
    repost_count = ads["dedup_key"].map(counts).where(ads["dedup_key"].ne(""), 1).astype(np.int64)
    return ads.assign(repost_count=repost_count.to_numpy()).reset_index(drop=True)


def read_groups_csv(path: Path) -> dict[int, dict]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as source:
        return {int(row["group_id"]): row for row in csv.DictReader(source)}


def title_from_file(source_file: str) -> str:
    stem = source_file.removesuffix(".jsonl").removeprefix("group_")
    stem = stem.removeprefix("unmatched_")
    return stem.replace("_", " ").strip() or source_file


def group_catalog(posts: pd.DataFrame, csv_rows: dict[int, dict], files: list[str]) -> pd.DataFrame:
    """Title and home location per source file: csv title, else the most common header group name."""
    names = posts.loc[posts["group_name"].notna(), ["source_file", "group_name"]]
    common = names.groupby("source_file")["group_name"].agg(lambda values: values.value_counts().index[0])
    records = []
    for source_file in sorted(set(files) | set(posts["source_file"].unique())):
        group_id = group_id_from_source(source_file)
        row = csv_rows.get(group_id) if group_id is not None else None
        title = (row or {}).get("group_title") or common.get(source_file) or title_from_file(source_file)
        records.append({
            "source_file": source_file,
            "group_id": group_id,
            "title": title,
            "home_province": (row or {}).get("province") or None,
            "home_city": (row or {}).get("city") or None,
        })
    columns = ["source_file", "group_id", "title", "home_province", "home_city"]
    return pd.DataFrame(records, columns=columns).set_index("source_file")


def code_hash(groups_csv: Path) -> str:
    """Changes whenever the extractor, the utilities it calls, or telegram_groups.csv change."""
    digest = hashlib.sha256(f"schema={SCHEMA_VERSION}".encode())
    for name in CACHE_INPUTS:
        digest.update(name.encode())
        digest.update((PROJECT_ROOT / name).read_bytes())
    digest.update(groups_csv.read_bytes() if groups_csv.is_file() else b"")
    return digest.hexdigest()


def complete_lines(data: bytes, first_line_no: int, max_bytes: int) -> list[tuple[int, int, int]]:
    """Split newline-terminated data into (start, end, first_line_no) pieces of about max_bytes."""
    pieces = []
    start, line_no = 0, first_line_no
    while start < len(data):
        end = data.rfind(b"\n", start, start + max_bytes) + 1
        if end <= start:
            end = data.index(b"\n", start) + 1
        pieces.append((start, end, line_no))
        line_no += data.count(b"\n", start, end)
        start = end
    return pieces


class Store:
    """Rows of every data/raw/group_*.jsonl file, read incrementally."""

    def __init__(
        self,
        config: ApiConfig,
        on_status: Callable[[dict], None] | None = None,
        on_update: Callable[[dict], None] | None = None,
    ):
        self.config = config
        self.on_status = on_status
        self.on_update = on_update
        self.status = "loading"
        self.progress = 0.0
        self.error: str | None = None
        self.csv_rows = read_groups_csv(config.groups_csv)
        self.files: dict[str, FileState] = {}
        self.seen: dict[str, set[int]] = {}
        self.snapshot = self._make_snapshot(0, with_derived(empty_rows()), None)
        self.dirty = False
        self.last_save = 0.0
        self._last_status = 0.0
        self._lock = threading.Lock()

    # -- public ------------------------------------------------------------------------------

    @property
    def cache_path(self) -> Path:
        return self.config.cache_dir / CACHE_FILE

    def health(self) -> dict:
        snapshot = self.snapshot
        return {
            "status": self.status,
            "progress": round(self.progress, 4),
            "version": snapshot.version,
            "posts": len(snapshot.posts),
            "unique_ads": len(snapshot.ads),
            "files": snapshot.files,
            "last_update": snapshot.last_update.isoformat() if snapshot.last_update else None,
            "last_post": snapshot.last_post.isoformat() if snapshot.last_post else None,
        }

    def load(self) -> None:
        """Warm start from the snapshot cache (then read only new bytes), else a full build."""
        with self._lock:
            started = time.perf_counter()
            restored = self.config.use_cache and self._restore_cache()
            if restored:
                log.info("restored %s posts from cache in %.1fs", f"{len(self.snapshot.posts):,}",
                         time.perf_counter() - started)
                self._poll(publish=False)
            else:
                self._build()
            self.status, self.progress = "ready", 1.0
            if self.dirty or not restored:
                self.save_cache(force=True)
            log.info("store ready: %s posts, %s unique ads in %.1fs", f"{len(self.snapshot.posts):,}",
                     f"{len(self.snapshot.ads):,}", time.perf_counter() - started)
        self._emit_status(force=True)

    def poll(self) -> dict | None:
        """Read lines appended since the last call; returns the update event payload if rows changed."""
        with self._lock:
            update = self._poll(publish=True)
            if self.dirty and time.monotonic() - self.last_save >= self.config.save_interval:
                self.save_cache()
        return update

    def run(self, stop: threading.Event) -> None:
        """Ingest-thread body: load, then poll every `poll_seconds` until `stop` is set."""
        while not stop.is_set():
            try:
                self.load()
                break
            except Exception as error:  # keep answering /api/health while retrying
                log.exception("initial load failed, retrying in 10 s")
                self.error = repr(error)
                stop.wait(10)
        self.error = None
        while not stop.wait(self.config.poll_seconds):
            try:
                self.poll()
            except Exception:
                log.exception("poll failed")
        if self.dirty:
            self.save_cache(force=True)

    def save_cache(self, force: bool = False) -> bool:
        """Write the snapshot to the cache directory (temp file + atomic replace)."""
        if not self.config.use_cache or not (force or self.dirty):
            return False
        snapshot = self.snapshot
        payload = {
            "schema": SCHEMA_VERSION,
            "code_hash": code_hash(self.config.groups_csv),
            "raw_dir": str(self.config.raw_dir.resolve()),
            "version": snapshot.version,
            "last_update": snapshot.last_update,
            "files": {name: asdict(state) for name, state in self.files.items()},
            "posts": snapshot.posts[list(extract.COLUMNS)],
        }
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_name(f".{CACHE_FILE}.{os.getpid()}.tmp")
        try:
            with temporary.open("wb") as target:
                pickle.dump(payload, target, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(temporary, self.cache_path)
        finally:
            temporary.unlink(missing_ok=True)
        self.dirty, self.last_save = False, time.monotonic()
        return True

    # -- loading -----------------------------------------------------------------------------

    def _raw_files(self) -> dict[str, Path]:
        if not self.config.raw_dir.is_dir():
            return {}
        return {path.name: path for path in sorted(self.config.raw_dir.glob("group_*.jsonl")) if path.is_file()}

    def _restore_cache(self) -> bool:
        if not self.cache_path.is_file():
            return False
        try:
            with self.cache_path.open("rb") as source:
                payload = pickle.load(source)
            valid = (
                payload.get("schema") == SCHEMA_VERSION
                and payload.get("code_hash") == code_hash(self.config.groups_csv)
                and payload.get("raw_dir") == str(self.config.raw_dir.resolve())
            )
        except Exception:
            log.warning("ignoring unreadable cache %s", self.cache_path, exc_info=True)
            return False
        if not valid:
            log.info("cache %s is stale, rebuilding", self.cache_path)
            return False
        posts = payload["posts"]
        self.files = {name: FileState(**state) for name, state in payload["files"].items()}
        self.seen = {
            name: set(ids.dropna().astype(np.int64).tolist())
            for name, ids in posts.groupby("source_file", sort=False)["msg_id"]
        }
        self.snapshot = self._make_snapshot(payload["version"], with_derived(posts), payload["last_update"])
        return True

    def _build(self) -> None:
        """Cold build: every file through the process pool."""
        self.files, self.seen = {}, {}
        ranges = []
        for name, path in self._raw_files().items():
            stat = path.stat()
            data = path.read_bytes()[: stat.st_size]
            end = data.rfind(b"\n") + 1
            self.files[name] = FileState(stat.st_ino, stat.st_size, end, data.count(b"\n", 0, end),
                                         data[max(0, end - TAIL_BYTES):end])
            ranges += [(str(path), start, stop, line) for start, stop, line in complete_lines(data[:end], 1, CHUNK_BYTES)]
        rows = self._extract_ranges(ranges, use_pool=True)
        posts = self._drop_seen(rows)
        self.snapshot = self._make_snapshot(self.snapshot.version + 1, with_derived(posts),
                                            datetime.now(UTC) if len(posts) else None)
        self.dirty = True

    def _extract_ranges(self, ranges: list[tuple[str, int, int, int]], use_pool: bool) -> pd.DataFrame:
        total = sum(end - start for _, start, end, _ in ranges) or 1
        results: dict[int, dict[str, list]] = {}
        done = 0
        if use_pool and len(ranges) > 1 and self.config.workers > 1:
            with ProcessPoolExecutor(
                max_workers=min(self.config.workers, len(ranges)),
                mp_context=get_context("spawn"),
                initializer=extract.init_worker,
                initargs=(str(self.config.groups_csv),),
            ) as pool:
                futures = {pool.submit(extract.extract_range, *task): index for index, task in enumerate(ranges)}
                for future in as_completed(futures):
                    index = futures[future]
                    results[index] = future.result()
                    done += ranges[index][2] - ranges[index][1]
                    self._set_progress(done / total)
        else:
            extract.init_worker(str(self.config.groups_csv))
            for index, task in enumerate(ranges):
                results[index] = extract.extract_range(*task)
                done += task[2] - task[1]
                self._set_progress(done / total)
        merged = {name: [] for name in extract.COLUMNS}
        for index in sorted(results):
            for name in extract.COLUMNS:
                merged[name].extend(results[index][name])
        return rows_frame(merged)

    # -- polling -----------------------------------------------------------------------------

    def _read_new(self) -> tuple[Batch, list[tuple[str, int, int, int]]]:
        """Stat every file and collect the complete lines written since the last read."""
        batch, ranges = Batch(), []
        current = self._raw_files()
        for name in set(self.files) - set(current):
            batch.removed_files.add(name)
        for name, path in current.items():
            try:
                stat = path.stat()
                state = self.files.get(name)
                if state is not None and (stat.st_ino != state.inode or stat.st_size < state.offset or (
                        stat.st_size != state.size and not self._tail_matches(path, state))):
                    batch.reset_files.add(name)
                    state = None
                if state is None:
                    state = FileState(stat.st_ino, 0)
                if stat.st_size == state.offset:
                    self.files[name] = FileState(stat.st_ino, stat.st_size, state.offset, state.lines, state.tail)
                    continue
                with path.open("rb") as source:
                    source.seek(state.offset)
                    data = source.read(stat.st_size - state.offset)
            except FileNotFoundError:
                batch.removed_files.add(name)
                continue
            end = data.rfind(b"\n") + 1
            if end:
                ranges += [(str(path), state.offset + start, state.offset + stop, line)
                           for start, stop, line in complete_lines(data[:end], state.lines + 1, CHUNK_BYTES)]
                tail = (state.tail + data[:end])[-TAIL_BYTES:]
                state = FileState(stat.st_ino, stat.st_size, state.offset + end,
                                  state.lines + data.count(b"\n", 0, end), tail)
            else:
                state = FileState(stat.st_ino, stat.st_size, state.offset, state.lines, state.tail)
            self.files[name] = state
        for name in batch.removed_files:
            self.files.pop(name, None)
        return batch, ranges

    @staticmethod
    def _tail_matches(path: Path, state: FileState) -> bool:
        if not state.tail:
            return True
        with path.open("rb") as source:
            source.seek(state.offset - len(state.tail))
            return source.read(len(state.tail)) == state.tail

    def _poll(self, publish: bool) -> dict | None:
        batch, ranges = self._read_new()
        dropped = batch.reset_files | batch.removed_files
        if not ranges and not dropped:
            return None
        new_bytes = sum(end - start for _, start, end, _ in ranges)
        rows = self._extract_ranges(ranges, use_pool=new_bytes >= POOL_MIN_BYTES) if ranges else empty_rows()
        old = self.snapshot
        posts = old.posts
        if dropped:
            posts = posts.loc[~posts["source_file"].isin(dropped)].reset_index(drop=True)
            for name in dropped:
                self.seen.pop(name, None)
        rows = self._drop_seen(rows)
        if not len(rows) and not dropped:
            return None
        posts = concat_rows([posts, with_derived(rows)])
        now = datetime.now(UTC)
        self.snapshot = self._make_snapshot(old.version + 1, posts, now if len(rows) else old.last_update)
        self.dirty = True
        update = self._update_event(old, self.snapshot, rows, now)
        if publish and self.on_update:
            self.on_update(update)
        return update

    def _drop_seen(self, rows: pd.DataFrame) -> pd.DataFrame:
        """Ignore a repeated (source_file, msg_id): the same message written twice."""
        keep = np.ones(len(rows), dtype=bool)
        for index, (name, msg_id) in enumerate(zip(rows["source_file"], rows["msg_id"])):
            if msg_id is pd.NA:
                continue
            seen = self.seen.setdefault(name, set())
            if msg_id in seen:
                keep[index] = False
            else:
                seen.add(msg_id)
        return rows if keep.all() else rows.loc[keep].reset_index(drop=True)

    @staticmethod
    def _update_event(old: Snapshot, new: Snapshot, rows: pd.DataFrame, now: datetime) -> dict:
        added = new.ads["row_id"].isin(rows["row_id"])
        known = new.ads["dedup_key"].isin(old.ads.loc[old.ads["dedup_key"].ne(""), "dedup_key"])
        fresh = new.ads.loc[added & ~known]
        provinces = fresh["region"].value_counts()
        return {
            "version": new.version,
            "added_posts": len(rows),
            "added_ads": len(fresh),
            "posts": len(new.posts),
            "unique_ads": len(new.ads),
            "at": now.isoformat(),
            "provinces": {name: int(count) for name, count in provinces.items() if count},
        }

    # -- helpers -----------------------------------------------------------------------------

    def _make_snapshot(self, version: int, posts: pd.DataFrame, last_update: datetime | None) -> Snapshot:
        last_post = posts["date"].max() if len(posts) else None
        return Snapshot(
            version=version,
            posts=posts,
            ads=unique_ads(posts),
            groups=group_catalog(posts, self.csv_rows, list(self.files)),
            files=len(self.files),
            last_update=last_update,
            last_post=None if last_post is None or pd.isna(last_post) else last_post.to_pydatetime(),
        )

    def _set_progress(self, value: float) -> None:
        if self.status == "loading":
            self.progress = min(max(value, self.progress), 0.99)
            self._emit_status()

    def _emit_status(self, force: bool = False) -> None:
        now = time.monotonic()
        if self.on_status and (force or now - self._last_status >= STATUS_INTERVAL):
            self._last_status = now
            self.on_status(self.health())
