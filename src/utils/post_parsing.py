"""Split forwarded Ish e'lonlari posts into header fields and the original job text."""

import re

import pandas as pd
from sklearn.preprocessing import FunctionTransformer

HEADER_PATTERN = re.compile(
    r"Yangi xabar ma'lumotlari:\s*"
    r"Guruh:\s*(?P<group_name>[^\n]*)\n"
    r"Xabar egasi:\s*(?P<author>[^\n]*)\n"
    r"Xabar vaqti:\s*(?P<posted_at>[^\n]*)\n\s*"
    r"Xabar matni:\s*\n?",
)
BOT_FOOTER_PATTERN = re.compile(r"\s*@muslim_vegukin_bot\b")
FILLED_PATTERN = re.compile(r"[✅⚠️\s]*BU ISHGA ODAM OLINDI!?", re.IGNORECASE)
PRIVATE_GROUP_PATTERN = re.compile(r"^🔒\s*|\s*\(Yopiq Guruh\)\s*$")


def parse_post(text: str) -> dict:
    """Return the header fields, cleaned job text, and whether the post was marked as filled.

    Posts written directly in a group (no Ish e'lonlari header) keep their text as `body`.
    `posted_at` is the original posting time in Korean time (KST), as printed by the bot.
    """
    text = text if isinstance(text, str) else ""
    header = HEADER_PATTERN.search(text)
    body = text[header.end():] if header else text
    is_filled = bool(FILLED_PATTERN.search(body))
    body = FILLED_PATTERN.sub("", BOT_FOOTER_PATTERN.sub("", body)).strip()
    return {
        "group_name": PRIVATE_GROUP_PATTERN.sub("", header["group_name"]).strip() if header else None,
        "author": header["author"].strip() if header else None,
        "posted_at": header["posted_at"].strip() if header else None,
        "is_private_group": bool(header and "Yopiq Guruh" in header["group_name"]),
        "is_filled": is_filled,
        "body": body,
    }


def post_body(text: str) -> str:
    """Return only the original job text."""
    return parse_post(text)["body"]


def parse_posts(texts: pd.Series) -> pd.DataFrame:
    """Parse a column of posts into one column per field, aligned with the input index."""
    return pd.DataFrame([parse_post(text) for text in texts], index=texts.index)


def _bodies(X):
    if isinstance(X, pd.DataFrame):
        return X.apply(lambda column: column.map(post_body))
    return pd.Series(X).map(post_body) if not isinstance(X, pd.Series) else X.map(post_body)


def post_body_transformer() -> FunctionTransformer:
    """Pipeline step that replaces each post with its job text only."""
    return FunctionTransformer(_bodies, feature_names_out="one-to-one")
