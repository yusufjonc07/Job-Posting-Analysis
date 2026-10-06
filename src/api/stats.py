"""Pure aggregations behind every stats endpoint: (snapshot, filters, now) -> JSON-ready dict.

Ads are the representative rows of `Snapshot.ads`; filters apply to them after dedup. Days, weeks,
months, quarters and years are Korea time. Every number is a plain Python int/float or None.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import numpy as np
import pandas as pd

from src.api.extract import OCCUPATION_NAMES, VISA_TYPES, decode_mask
from src.api.store import KST_OFFSET_SECONDS, PERIODS, PROVINCE_IDS, SCRIPTS, Snapshot, display_title
from src.utils.salary import PERIOD_RANGES

PROVINCE_NAMES_KO = {
    "Seoul": "서울", "Busan": "부산", "Daegu": "대구", "Incheon": "인천", "Gwangju": "광주",
    "Daejeon": "대전", "Ulsan": "울산", "Sejong": "세종", "Gyeonggi-do": "경기", "Gangwon-do": "강원",
    "Chungcheongbuk-do": "충북", "Chungcheongnam-do": "충남", "Jeollabuk-do": "전북",
    "Jeollanam-do": "전남", "Gyeongsangbuk-do": "경북", "Gyeongsangnam-do": "경남", "Jeju-do": "제주",
}
FROM_POST = ("address", "text")
BIN_WIDTHS = {"hourly": 500, "daily": 10_000, "monthly": 100_000}
MIN_REGION_DAILY_PAY = 10
MIN_TREND_ADS = 30
MIN_PROVINCE_PAY_ADS = 30
LENGTH_EDGES = np.logspace(0, 4, 41)
REPOST_BUCKETS = (
    ("once", 1, 1), ("2 times", 2, 2), ("3–5 times", 3, 5), ("6–20 times", 6, 20),
    ("21–100 times", 21, 100), ("100+ times", 101, None),
)
FLAGS = (
    ("is_forwarded", "Forwarded"), ("has_phone", "Phone number"), ("has_salary", "Salary stated"),
    ("is_filled", "Marked filled"), ("has_url", "Link"),
)
OCCUPATION_BITS = np.array([1 << index for index in range(len(OCCUPATION_NAMES))], dtype=np.int32)
VISA_BITS = np.array([1 << index for index in range(len(VISA_TYPES))], dtype=np.int32)


@dataclass(frozen=True)
class Filters:
    days: int | None = None
    source: Literal["all", "direct", "forwarded"] = "all"
    basis: Literal["all", "post"] = "all"

    @property
    def region_column(self) -> str:
        return "region_post" if self.basis == "post" else "region"


# -- helpers ---------------------------------------------------------------------------------

def share(part: float, whole: float) -> float:
    return round(float(part) / whole, 4) if whole else 0.0


def number(value) -> float | None:
    """A JSON number from a pandas/numpy scalar; NaN becomes None, whole numbers become int."""
    if value is None or pd.isna(value):
        return None
    value = float(value)
    return int(value) if value.is_integer() else round(value, 2)


def iso(moment) -> str | None:
    return None if moment is None or pd.isna(moment) else pd.Timestamp(moment).isoformat()


def kst_day(moment: datetime) -> int:
    return int((moment.timestamp() + KST_OFFSET_SECONDS) // 86_400)


def by_source(frame: pd.DataFrame, filters: Filters) -> pd.DataFrame:
    if filters.source == "direct":
        return frame.loc[~frame["is_forwarded"]]
    if filters.source == "forwarded":
        return frame.loc[frame["is_forwarded"]]
    return frame


def in_window(frame: pd.DataFrame, filters: Filters, now: datetime) -> pd.DataFrame:
    frame = by_source(frame, filters)
    if filters.days is None:
        return frame
    return frame.loc[frame["date"] >= now - timedelta(days=filters.days)]


def select_ads(snapshot: Snapshot, filters: Filters, now: datetime) -> pd.DataFrame:
    return in_window(snapshot.ads, filters, now)


def region_counts(ads: pd.DataFrame, filters: Filters) -> pd.Series:
    """Ads per map region in the fixed province order (zeros included)."""
    return ads[filters.region_column].value_counts(sort=False).reindex(PROVINCE_IDS, fill_value=0)


def quartiles(values: pd.Series) -> tuple[float | None, float | None, float | None]:
    if values.empty:
        return None, None, None
    q1, median, q3 = (round(value) for value in values.quantile([0.25, 0.5, 0.75]).tolist())
    return median, q1, q3


def mask_counts(masks: pd.Series, bits: np.ndarray) -> np.ndarray:
    if masks.empty:
        return np.zeros(len(bits), dtype=np.int64)
    return ((masks.to_numpy()[:, None] & bits) != 0).sum(axis=0)


def named_counts(masks: pd.Series, bits: np.ndarray, names: tuple[str, ...], total: int | None = None) -> list[dict]:
    """[{name, ads[, share]}] sorted by count, descending."""
    counts = mask_counts(masks, bits)
    rows = [{"name": name, "ads": int(count)} for name, count in zip(names, counts)]
    if total is not None:
        for row in rows:
            row["share"] = share(row["ads"], total)
    return sorted(rows, key=lambda row: -row["ads"])


# -- time buckets ----------------------------------------------------------------------------

def granularity_for(days: int | None) -> str:
    if days is not None and days <= 31:
        return "day"
    if days is not None and days <= 180:
        return "week"
    return "month"


def bucket_start(days: np.ndarray, granularity: str) -> np.ndarray:
    """Start of the day/week (Monday)/month containing each Korea-time day number."""
    dates = days.astype("datetime64[D]")
    if granularity == "week":
        return dates - ((days - 4) % 7).astype("timedelta64[D]")  # day 0 (1970-01-01) was a Thursday
    if granularity == "month":
        return dates.astype("datetime64[M]").astype("datetime64[D]")
    return dates


def bucket_range(first: int, last: int, granularity: str) -> np.ndarray:
    start, end = bucket_start(np.array([first, last]), granularity)
    if granularity == "month":
        return np.arange(start.astype("datetime64[M]"), end.astype("datetime64[M]") + np.timedelta64(1, "M")).astype("datetime64[D]")
    step = np.timedelta64(7 if granularity == "week" else 1, "D")
    return np.arange(start, end + np.timedelta64(1, "D"), step)


def time_series(frame: pd.DataFrame, filters: Filters, now: datetime, columns: dict[str, pd.Series]) -> dict:
    """Counts per bucket for each named boolean column; buckets cover the window without gaps."""
    granularity = granularity_for(filters.days)
    dated = frame["date"].notna().to_numpy()
    days = frame["kst_day"].to_numpy()[dated]
    if filters.days is not None:
        first, last = kst_day(now - timedelta(days=filters.days)), kst_day(now)
    elif len(days):
        first, last = int(days.min()), int(days.max())
    else:
        return {"granularity": granularity, "points": []}
    buckets = bucket_range(first, last, granularity)
    starts = bucket_start(days, granularity)
    positions = np.searchsorted(buckets, starts)
    valid = (positions < len(buckets)) & (buckets[np.minimum(positions, len(buckets) - 1)] == starts)
    counts = {
        name: np.bincount(positions[valid & values.to_numpy()[dated]], minlength=len(buckets))
        for name, values in columns.items()
    }
    points = [
        {"t": str(bucket), **{name: int(counts[name][index]) for name in columns}}
        for index, bucket in enumerate(buckets)
    ]
    return {"granularity": granularity, "points": points}


# -- shared row builders ---------------------------------------------------------------------

def feed_items(ads: pd.DataFrame, groups: pd.DataFrame, limit: int) -> list[dict]:
    """Newest representatives first, shaped as FeedItem."""
    newest = ads.sort_values(["date", "row_id"], ascending=False, na_position="last").head(limit)
    titles = groups["title"]
    items = []
    for row in newest.itertuples(index=False):
        forwarded_from = display_title(row.group_name) if row.is_forwarded else None
        title = forwarded_from or titles.get(row.source_file, row.source_file)
        period = row.salary_period if isinstance(row.salary_period, str) else None
        items.append({
            "id": row.row_id,
            "date": iso(row.date),
            "group_title": title,
            "province": row.region if isinstance(row.region, str) else None,
            "city": row.city if isinstance(row.city, str) and row.city else None,
            "location_source": row.location_source,
            "salary": {"amount": number(row.salary_krw), "period": period} if period and not pd.isna(row.salary_krw) else None,
            "occupations": decode_mask(int(row.occupations), OCCUPATION_NAMES),
            "visas": decode_mask(int(row.visas), VISA_TYPES),
            "excerpt": row.excerpt,
            "is_forwarded": bool(row.is_forwarded),
            "repost_count": int(row.repost_count),
        })
    return items


def source_split(ads: pd.DataFrame) -> dict[str, int]:
    counts = ads["location_source"].value_counts()
    return {name: int(counts.get(name, 0)) for name in ("address", "text", "group")}


def pay_summary(ads: pd.DataFrame) -> list[dict]:
    rows = []
    for period in PERIODS:
        values = ads.loc[ads["salary_period"] == period, "salary_krw"].dropna()
        median, q1, q3 = quartiles(values)
        rows.append({"period": period, "ads": int(len(values)), "median": median, "q1": q1, "q3": q3})
    return rows


# -- endpoints -------------------------------------------------------------------------------

def meta(snapshot: Snapshot) -> dict:
    dates = snapshot.posts["date"]
    return {
        "version": snapshot.version,
        "provinces": [{"id": province, "name_ko": PROVINCE_NAMES_KO[province]} for province in PROVINCE_IDS],
        "date_min": iso(dates.min()) if len(dates) else None,
        "date_max": iso(dates.max()) if len(dates) else None,
        "groups": int(len(snapshot.groups)),
    }


def overview(snapshot: Snapshot, filters: Filters, now: datetime) -> dict:
    ads = select_ads(snapshot, filters, now)
    posts = in_window(snapshot.posts, filters, now)
    recent = by_source(snapshot.ads, filters)["date"]
    total = len(ads)
    pay = {row["period"]: row["median"] for row in pay_summary(ads)}
    regions = region_counts(ads, filters).sort_values(ascending=False, kind="stable")
    return {
        "version": snapshot.version,
        "kpis": {
            "unique_ads": total,
            "posts": int(len(posts)),
            "repost_share": max(round(1 - total / len(posts), 4), 0.0) if len(posts) else 0.0,
            "last_24h": int((recent >= now - timedelta(hours=24)).sum()),
            "last_7d": int((recent >= now - timedelta(days=7)).sum()),
            "prev_7d": int(((recent >= now - timedelta(days=14)) & (recent < now - timedelta(days=7))).sum()),
            "salary_share": share(ads["salary_krw"].notna().sum(), total),
            "median_pay": pay,
            "located_share": share(ads["location_source"].isin(FROM_POST).sum(), total),
            "forwarded_share": share(ads["is_forwarded"].sum(), total),
        },
        "volume": time_series(ads, filters, now, {"direct": ~ads["is_forwarded"], "forwarded": ads["is_forwarded"]}),
        "top_provinces": [{"province": name, "ads": int(count)} for name, count in regions.head(5).items() if count],
    }


def locations(snapshot: Snapshot, filters: Filters, now: datetime) -> dict:
    ads = select_ads(snapshot, filters, now)
    column = filters.region_column
    counts = region_counts(ads, filters)
    placed = int(counts.sum())
    daily = ads.loc[ads["salary_period"] == "daily"].groupby(column, observed=True)["salary_krw"].agg(["median", "size"])
    split = ads.groupby([column, "location_source"], observed=False).size()
    provinces = []
    for province in PROVINCE_IDS:
        pay = daily.loc[province] if province in daily.index else None
        provinces.append({
            "province": province,
            "name_ko": PROVINCE_NAMES_KO[province],
            "ads": int(counts[province]),
            "share": share(counts[province], placed),
            "by_source": {name: int(split.get((province, name), 0)) for name in ("address", "text", "group")},
            "median_daily_pay": number(pay["median"]) if pay is not None and pay["size"] >= MIN_REGION_DAILY_PAY else None,
        })
    province = ads["province"]
    nationwide = int((province == "Nationwide").sum())
    on_map = province.isin(PROVINCE_IDS)
    group_fallback = int((on_map & ads[column].isna()).sum())
    sources = ads["location_source"].value_counts()
    return {
        "version": snapshot.version,
        "total": len(ads),
        "provinces": provinces,
        "unplaced": {
            "nationwide": nationwide,
            "unknown": int((~on_map).sum()) - nationwide,
            "group_fallback": group_fallback,
        },
        "sources": {name: int(sources.get(name, 0)) for name in ("address", "text", "group", "unknown")},
    }


def region(snapshot: Snapshot, filters: Filters, now: datetime, province: str) -> dict:
    ads = select_ads(snapshot, filters, now)
    counts = region_counts(ads, filters)
    selected = ads.loc[ads[filters.region_column] == province]
    total = len(selected)
    cities = selected["city"].fillna("").replace("", "Unspecified").value_counts().head(10)
    scripts = selected["script"].value_counts()
    per_group = (
        selected.groupby("source_file", sort=False)["date"].agg(["size", "max"])
        .sort_values(["size", "max"], ascending=False).head(10)
    )
    groups = []
    for source_file, row in per_group.iterrows():
        info = snapshot.groups.loc[source_file] if source_file in snapshot.groups.index else None
        groups.append({
            "group_id": None if info is None or pd.isna(info["group_id"]) else int(info["group_id"]),
            "source_file": source_file,
            "title": info["title"] if info is not None else source_file,
            "home_province": info["home_province"] if info is not None else None,
            "ads": int(row["size"]),
            "last_post": iso(row["max"]),
        })
    return {
        "version": snapshot.version,
        "province": province,
        "name_ko": PROVINCE_NAMES_KO[province],
        "ads": total,
        "rank": int((counts > counts[province]).sum()) + 1,
        "share": share(total, counts.sum()),
        "trend": time_series(selected, filters, now, {"ads": pd.Series(True, index=selected.index)}),
        "by_source": source_split(selected),
        "cities": [{"city": city, "ads": int(count)} for city, count in cities.items()],
        "pay": pay_summary(selected),
        "occupations": named_counts(selected["occupations"], OCCUPATION_BITS, OCCUPATION_NAMES),
        "visas": [row for row in named_counts(selected["visas"], VISA_BITS, VISA_TYPES) if row["ads"]],
        "scripts": {name: share(scripts.get(name, 0), total) for name in SCRIPTS},
        "groups": groups,
        "latest": feed_items(selected, snapshot.groups, 5),
    }


def feed(snapshot: Snapshot, filters: Filters, now: datetime, limit: int, province: str | None) -> dict:
    ads = select_ads(snapshot, filters, now)
    if province is not None:
        ads = ads.loc[ads[filters.region_column] == province]
    return {"version": snapshot.version, "items": feed_items(ads, snapshot.groups, limit)}


def quarter_label(start: np.datetime64) -> str:
    month = start.astype("datetime64[M]").astype(int)
    return f"{1970 + month // 12}Q{month % 12 // 3 + 1}"


def pay(snapshot: Snapshot, filters: Filters, now: datetime) -> dict:
    ads = select_ads(snapshot, filters, now)
    salaried = ads.loc[ads["salary_krw"].notna() & ads["salary_period"].notna() & ads["date"].notna()]
    periods = []
    for period in PERIODS:
        values = salaried.loc[salaried["salary_period"] == period, "salary_krw"]
        low, high = PERIOD_RANGES[period]
        width = BIN_WIDTHS[period]
        edges = np.arange(low, high + width, width)
        histogram, _ = np.histogram(values.to_numpy(), bins=edges)
        median, q1, q3 = quartiles(values)
        periods.append({
            "period": period, "ads": int(len(values)), "median": median, "q1": q1, "q3": q3, "bin_width": width,
            "bins": [{"x0": int(x0), "x1": int(x1), "ads": int(count)} for x0, x1, count in zip(edges[:-1], edges[1:], histogram)],
        })

    months = salaried["kst_day"].to_numpy().astype("datetime64[D]").astype("datetime64[M]").astype(int)
    quarters = months - months % 3
    local = now + timedelta(seconds=KST_OFFSET_SECONDS)
    current = ((local.year - 1970) * 12 + local.month - 1) // 3 * 3
    complete = quarters < current
    trend = []
    span = np.arange(quarters[complete].min(), quarters[complete].max() + 1, 3) if complete.any() else np.array([], dtype=int)
    for period in PERIODS:
        chosen = complete & (salaried["salary_period"] == period).to_numpy()
        values = pd.Series(salaried["salary_krw"].to_numpy()[chosen]).groupby(quarters[chosen]).agg(["median", "size"])
        points = []
        for quarter in span:
            start = np.datetime64(int(quarter), "M")
            ads_in_quarter = int(values.loc[quarter, "size"]) if quarter in values.index else 0
            median = number(values.loc[quarter, "median"]) if ads_in_quarter >= MIN_TREND_ADS else None
            points.append({"t": str(start.astype("datetime64[D]")), "quarter": quarter_label(start),
                           "ads": ads_in_quarter, "median": median})
        trend.append({"period": period, "points": points})

    daily = salaried.loc[salaried["salary_period"] == "daily"]
    by_province = []
    for province, values in daily.groupby(filters.region_column, observed=True)["salary_krw"]:
        if len(values) >= MIN_PROVINCE_PAY_ADS:
            median, q1, q3 = quartiles(values)
            by_province.append({"province": province, "ads": int(len(values)), "median": median, "q1": q1, "q3": q3})
    by_province.sort(key=lambda row: -row["median"])
    return {"version": snapshot.version, "periods": periods, "trend": trend, "by_province": by_province}


def jobs(snapshot: Snapshot, filters: Filters, now: datetime) -> dict:
    ads = select_ads(snapshot, filters, now)
    total = len(ads)
    column = filters.region_column
    top = region_counts(ads, filters).sort_values(ascending=False, kind="stable").head(10)
    top = [name for name, count in top.items() if count]
    cells = [mask_counts(ads.loc[ads[column] == name, "occupations"], OCCUPATION_BITS).tolist() for name in top]
    return {
        "version": snapshot.version,
        "named_share": share((ads["occupations"] != 0).sum(), total),
        "visa_share": share((ads["visas"] != 0).sum(), total),
        "occupations": named_counts(ads["occupations"], OCCUPATION_BITS, OCCUPATION_NAMES, total),
        "visas": [row for row in named_counts(ads["visas"], VISA_BITS, VISA_TYPES, total) if row["ads"]],
        "matrix": {"provinces": top, "occupations": list(OCCUPATION_NAMES), "cells": [[int(v) for v in row] for row in cells]},
    }


def posts(snapshot: Snapshot, filters: Filters, now: datetime) -> dict:
    ads = select_ads(snapshot, filters, now)
    total = len(ads)
    dated = ads.loc[ads["date"].notna()]
    years = 1970 + dated["kst_day"].to_numpy().astype("datetime64[D]").astype("datetime64[Y]").astype(int)
    by_year = pd.crosstab(years, dated["script"].to_numpy()) if len(dated) else pd.DataFrame()
    scripts = []
    for year, row in by_year.iterrows():
        count = row.sum()
        scripts.append({"year": int(year), **{name: share(row.get(name, 0), count) for name in SCRIPTS}})

    flags = {
        "is_forwarded": ads["is_forwarded"].sum(), "has_phone": ads["has_phone"].sum(),
        "has_salary": ads["salary_krw"].notna().sum(), "is_filled": ads["is_filled"].sum(), "has_url": ads["has_url"].sum(),
    }
    lengths = np.clip(ads["n_chars"].to_numpy(), LENGTH_EDGES[0], LENGTH_EDGES[-1])
    histogram, _ = np.histogram(lengths, bins=LENGTH_EDGES)

    reposts = ads["repost_count"].to_numpy()
    all_posts = int(reposts.sum())
    buckets = []
    for name, low, high in REPOST_BUCKETS:
        chosen = (reposts >= low) & (reposts <= (high if high is not None else np.iinfo(np.int64).max))
        count = int(reposts[chosen].sum())
        buckets.append({"bucket": name, "unique_ads": int(chosen.sum()), "posts": count, "share_of_posts": share(count, all_posts)})

    return {
        "version": snapshot.version,
        "scripts": scripts,
        "flags": [{"key": key, "label": label, "share": share(flags[key], total)} for key, label in FLAGS],
        "length": {
            "median": number(np.median(ads["n_chars"].to_numpy())) if total else 0,
            "bins": [{"x0": round(float(x0), 2), "x1": round(float(x1), 2), "ads": int(count)}
                     for x0, x1, count in zip(LENGTH_EDGES[:-1], LENGTH_EDGES[1:], histogram)],
        },
        "reposts": buckets,
    }


def groups(snapshot: Snapshot, filters: Filters, now: datetime) -> dict:
    ads = select_ads(snapshot, filters, now)
    posts_in_window = in_window(snapshot.posts, filters, now)
    post_stats = posts_in_window.groupby("source_file")["date"].agg(["size", "min", "max"])
    ad_stats = ads.assign(from_post=ads["location_source"].isin(FROM_POST)).groupby("source_file").agg(
        unique_ads=("row_id", "size"), forwarded=("is_forwarded", "sum"), from_post=("from_post", "sum"),
    )
    rows = []
    for source_file, info in snapshot.groups.iterrows():
        unique = int(ad_stats.at[source_file, "unique_ads"]) if source_file in ad_stats.index else 0
        has_posts = source_file in post_stats.index
        rows.append({
            "group_id": None if pd.isna(info["group_id"]) else int(info["group_id"]),
            "source_file": source_file,
            "title": info["title"],
            "home_province": info["home_province"],
            "home_city": info["home_city"],
            "posts": int(post_stats.at[source_file, "size"]) if has_posts else 0,
            "unique_ads": unique,
            "forwarded_share": share(ad_stats.at[source_file, "forwarded"], unique) if unique else 0.0,
            "placed_from_post_share": share(ad_stats.at[source_file, "from_post"], unique) if unique else 0.0,
            "first_post": iso(post_stats.at[source_file, "min"]) if has_posts else None,
            "last_post": iso(post_stats.at[source_file, "max"]) if has_posts else None,
        })
    rows.sort(key=lambda row: (-row["unique_ads"], -row["posts"], row["title"]))
    return {"version": snapshot.version, "groups": rows}


ENDPOINTS = {
    "overview": overview, "locations": locations, "pay": pay, "jobs": jobs, "posts": posts, "groups": groups,
}


def utc_now() -> datetime:
    return datetime.now(UTC)
