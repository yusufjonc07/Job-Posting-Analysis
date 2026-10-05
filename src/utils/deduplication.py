"""Find reposted job ads: the same text posted again, forwarded, or written in another script."""

import hashlib
import re

import pandas as pd

from src.utils.post_parsing import post_body
from src.utils.text_cleaning import clean_text

NON_WORD_PATTERN = re.compile(r"[^\w]+")


def dedup_key(text: str) -> str:
    """Hash of the job text ignoring header, case, script (Cyrillic/Latin), emoji, punctuation and spacing.

    Phones and numbers are kept, so the same template with a different wage or contact stays distinct.
    """
    normalized = clean_text(post_body(text), mask_phones=False, mask_mentions=False, mask_urls=False)
    normalized = NON_WORD_PATTERN.sub("", normalized)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest() if normalized else ""


def mark_duplicates(frame: pd.DataFrame, text_column: str = "text", date_column: str = "date") -> pd.DataFrame:
    """Add dedup_key, repost_count, and is_repost (every copy except the earliest one).

    Empty texts (media-only posts) get no key and are never marked as reposts.
    """
    frame = frame.copy()
    frame["dedup_key"] = frame[text_column].map(dedup_key)
    has_key = frame["dedup_key"].ne("")
    frame["repost_count"] = frame.groupby("dedup_key")["dedup_key"].transform("size").where(has_key, 1)
    order = frame.sort_values(date_column, kind="stable")
    frame["is_repost"] = order.duplicated("dedup_key", keep="first").reindex(frame.index) & has_key
    return frame


def drop_duplicates(frame: pd.DataFrame, text_column: str = "text", date_column: str = "date") -> pd.DataFrame:
    """Keep only the earliest copy of each ad; `repost_count` tells how often it was posted."""
    marked = mark_duplicates(frame, text_column, date_column)
    return marked.loc[~marked["is_repost"]]
