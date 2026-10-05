"""Extract advertised pay (KRW) and its period from Uzbek/Russian/Korean job posts."""

import re
from dataclasses import dataclass

import pandas as pd

from src.utils.transliteration import cyrillic_to_latin

# Multiplier per unit word, matched after transliteration and lower-casing.
UNITS: dict[str, int] = {
    "mln": 1_000_000, "million": 1_000_000, "milyon": 1_000_000, "mlin": 1_000_000,
    "man": 10_000, "만": 10_000,
    "ming": 1_000, "k": 1_000, "tis": 1_000, "tisyach": 1_000, "천": 1_000,
    "won": 1, "von": 1, "w": 1, "원": 1,
}
AMOUNT_PATTERN = re.compile(
    r"(?<![\d.,])(?P<number>\d+(?:[ .,]\d{3})+|\d+(?:[.,]\d+)?)\s*\.?\s*"
    r"(?P<unit>mln|million|milyon|mlin|man|만|ming|tisyach|tis|천|k|won|von|w|원)"
    r"(?![a-z])",
)
PERIOD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "hourly": ("soat", "soatiga", "chasov", "chas", "v chas", "시급", "시간", "hour"),
    "daily": ("kunlik", "kuniga", "kunga", "v den", "den", "일급", "일당", "하루", "daily", "dushanba",
              "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"),
    "monthly": ("oylik", "oyiga", "oyda", "mesyac", "v mesyac", "월급", "monthly", "month"),
}
# Plausible pay ranges in KRW; amounts outside every range (rent, food prices) are dropped.
PERIOD_RANGES: dict[str, tuple[int, int]] = {
    "hourly": (9_000, 30_000),
    "daily": (50_000, 500_000),
    "monthly": (1_000_000, 8_000_000),
}


@dataclass(frozen=True)
class Salary:
    amount_krw: int
    period: str          # hourly | daily | monthly
    period_source: str   # keyword (stated in the post) | magnitude (inferred from the amount)
    raw: str


def parse_number(number: str, unit: str) -> float:
    """Read "2.8", "3,5", "2800.000", "2 156 000", "140,000" as numbers."""
    if re.fullmatch(r"\d+(?:[ .,]\d{3})+", number):
        return float(re.sub(r"[ .,]", "", number))
    return float(number.replace(",", "."))


def _period_from_context(context: str) -> str | None:
    for period, keywords in PERIOD_KEYWORDS.items():
        if any(re.search(rf"(?<![a-z]){re.escape(keyword)}", context) for keyword in keywords):
            return period
    return None


def _period_from_magnitude(amount: int) -> str | None:
    for period, (low, high) in PERIOD_RANGES.items():
        if low <= amount < high:
            return period
    return None


def extract_salaries(text: str) -> list[Salary]:
    """Return every pay amount found in a post, in order of appearance."""
    if not isinstance(text, str):
        return []
    text = cyrillic_to_latin(text).lower()
    salaries = []
    for match in AMOUNT_PATTERN.finditer(text):
        amount = round(parse_number(match["number"], match["unit"]) * UNITS[match["unit"]])
        context = text[max(0, match.start() - 40):match.end() + 25]
        period = _period_from_context(context)
        source = "keyword"
        if period is not None and not PERIOD_RANGES[period][0] <= amount < PERIOD_RANGES[period][1]:
            period = None  # stated period contradicts the amount, e.g. "oylik" next to a bonus
        if period is None:
            period, source = _period_from_magnitude(amount), "magnitude"
        if period is not None:
            salaries.append(Salary(amount, period, source, match.group(0)))
    return salaries


def main_salary(text: str) -> Salary | None:
    """Pick the first amount with a stated period, else the first plausible amount."""
    salaries = extract_salaries(text)
    stated = [salary for salary in salaries if salary.period_source == "keyword"]
    return (stated or salaries or [None])[0]


def salary_columns(texts: pd.Series) -> pd.DataFrame:
    """Return salary_krw, salary_period and salary_period_source columns for a text column."""
    rows = []
    for text in texts:
        salary = main_salary(text)
        rows.append({
            "salary_krw": salary.amount_krw if salary else None,
            "salary_period": salary.period if salary else None,
            "salary_period_source": salary.period_source if salary else None,
        })
    return pd.DataFrame(rows, index=texts.index).astype({"salary_krw": "Int64"})
