"""Load raw posts and build the ColumnTransformer that turns them into model features.

Typical use:

    messages = load_messages()                      # one row per unique job offer
    preprocessor = build_preprocessor()
    model = make_pipeline(preprocessor, LogisticRegression(max_iter=1000))
    model.fit(messages[["text", "source_file"]], labels)

The transformer expects two raw columns: `text` (the Telegram message as crawled) and
`source_file` (the data/raw file name, used for the group-location fallback).
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import PROJECT_ROOT, settings
from src.utils.deduplication import mark_duplicates
from src.utils.job_filter import JOB_OFFER, classify_post
from src.utils.locations import load_group_locations, resolve_location
from src.utils.post_parsing import parse_post, post_body_transformer
from src.utils.salary import main_salary
from src.utils.text_cleaning import PHONE_PATTERN, URL_PATTERN, EMOJI_PATTERN, TextCleaner

GROUPS_CSV = PROJECT_ROOT / "data" / "telegram_groups.csv"
HANGUL_PATTERN = re.compile(r"[가-힣]")
CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁёЎўҚқҒғҲҳ]")
LETTER_PATTERN = re.compile(r"[^\W\d_]")

NUMERIC_FEATURES = [
    "log_length", "n_lines", "digit_ratio", "hangul_ratio", "cyrillic_ratio", "n_emoji",
    "has_phone", "has_url", "is_forwarded", "is_filled", "has_salary", "log_salary_krw",
]
CATEGORICAL_FEATURES = ["salary_period", "province", "location_source"]


def load_messages(raw_dir: Path = settings.raw_data_dir, drop_reposts: bool = True, jobs_only: bool = True) -> pd.DataFrame:
    """Read every data/raw/*.jsonl file into text, source_file, msg_id, date and kind columns.

    `kind` is src.utils.job_filter.classify_post (job_offer, job_seeker, cargo, travel, sale, service,
    chat); only job offers are kept unless jobs_only=False. Reposts (same job text posted again) are
    dropped by default; `repost_count` keeps how often each ad appeared. Media-only posts with no text
    are always dropped.
    """
    rows = []
    for path in sorted(Path(raw_dir).glob("group_*.jsonl")):
        with path.open(encoding="utf-8") as source:
            for line in source:
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows.append({
                    "source_file": path.name,
                    "msg_id": message.get("id"),
                    "date": pd.to_datetime(message.get("date"), utc=True, errors="coerce"),
                    "text": str(message.get("message") or ""),
                })
    messages = pd.DataFrame(rows)
    messages = messages[messages["text"].str.strip().ne("")]
    messages = messages.assign(kind=messages["text"].map(classify_post))
    if jobs_only:
        messages = messages[messages["kind"].eq(JOB_OFFER)]
    messages = mark_duplicates(messages, text_column="text", date_column="date")
    if drop_reposts:
        messages = messages[~messages["is_repost"]]
    return messages.reset_index(drop=True)


def _texts(X) -> pd.Series:
    """Accept a Series, a one-column DataFrame, or an array of texts."""
    if isinstance(X, pd.DataFrame):
        X = X.iloc[:, 0]
    return pd.Series(np.asarray(X, dtype=object).ravel()).fillna("").astype(str)


def numeric_post_features(X) -> pd.DataFrame:
    """Structure and salary signals computed from the raw post text."""
    rows = []
    for text in _texts(X):
        post = parse_post(text)
        body = post["body"]
        letters = max(len(LETTER_PATTERN.findall(body)), 1)
        salary = main_salary(body)
        rows.append([
            np.log1p(len(body)),
            body.count("\n") + 1,
            sum(char.isdigit() for char in body) / max(len(body), 1),
            len(HANGUL_PATTERN.findall(body)) / letters,
            len(CYRILLIC_PATTERN.findall(body)) / letters,
            len(EMOJI_PATTERN.findall(body)),
            float(bool(PHONE_PATTERN.search(body))),
            float(bool(URL_PATTERN.search(body))),
            float(post["author"] is not None),
            float(post["is_filled"]),
            float(salary is not None),
            np.log1p(salary.amount_krw) if salary else 0.0,
        ])
    return pd.DataFrame(rows, columns=NUMERIC_FEATURES)


def categorical_post_features(X, group_locations: dict[int, tuple[str, str]]) -> pd.DataFrame:
    """Salary period, province and how the province was found; needs `text` and `source_file`."""
    X = pd.DataFrame(X, columns=["text", "source_file"]) if not isinstance(X, pd.DataFrame) else X
    rows = []
    for text, source_file in zip(X["text"].fillna("").astype(str), X["source_file"].astype(str)):
        salary = main_salary(parse_post(text)["body"])
        province, _, location_source = resolve_location(text, source_file, group_locations)
        rows.append([salary.period if salary else "none", province or "unknown", location_source])
    return pd.DataFrame(rows, columns=CATEGORICAL_FEATURES)


def _numeric_names(transformer, input_features) -> np.ndarray:
    return np.array(NUMERIC_FEATURES, dtype=object)


def _categorical_names(transformer, input_features) -> np.ndarray:
    return np.array(CATEGORICAL_FEATURES, dtype=object)


def build_preprocessor(
    groups_csv: Path = GROUPS_CSV,
    word_max_features: int = 50_000,
    char_max_features: int = 50_000,
    min_df: int = 3,
) -> ColumnTransformer:
    """ColumnTransformer: word TF-IDF + char TF-IDF on cleaned text, numeric and categorical post features."""
    group_locations = load_group_locations(groups_csv)
    words = make_pipeline(
        post_body_transformer(),
        TextCleaner(mask_numbers=True),  # amounts are covered by the salary features
        TfidfVectorizer(ngram_range=(1, 2), min_df=min_df, max_features=word_max_features, sublinear_tf=True),
    )
    # Character n-grams within words cope with misspellings and Uzbek endings (tegu, teguga, tegudan).
    chars = make_pipeline(
        post_body_transformer(),
        TextCleaner(),
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=min_df,
                        max_features=char_max_features, sublinear_tf=True),
    )
    numeric = make_pipeline(
        FunctionTransformer(numeric_post_features, feature_names_out=_numeric_names),
        StandardScaler(),
    )
    categorical = make_pipeline(
        FunctionTransformer(
            categorical_post_features,
            kw_args={"group_locations": group_locations},
            feature_names_out=_categorical_names,
        ),
        OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=20),
    )
    return ColumnTransformer(
        [
            ("words", words, "text"),
            ("chars", chars, "text"),
            ("numeric", numeric, ["text"]),
            ("categorical", categorical, ["text", "source_file"]),
        ],
        remainder="drop",
        sparse_threshold=1.0,
    )
