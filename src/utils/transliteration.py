"""Cyrillic-to-Latin transliteration for Uzbek/Russian text, usable in scikit-learn pipelines."""

import re

import numpy as np
import pandas as pd
from sklearn.preprocessing import FunctionTransformer

# Official Uzbek Latin alphabet (1995), extended with Russian-only letters.
# "е" and "ц" depend on position and are handled in `cyrillic_to_latin`.
CYRILLIC_TO_LATIN: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ё": "yo", "ж": "j", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ч": "ch", "ш": "sh",
    "щ": "sh", "ъ": "'", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
}
VOWELS = set("аеёиоуэюяўАЕЁИОУЭЮЯЎ")
APOSTROPHES = re.compile(r"[ʻʼ‘’`´]")


def _is_upper_word(text: str, index: int) -> bool:
    """True when a capital letter sits in an ALL-CAPS word, so "Ш" becomes "SH" not "Sh"."""
    neighbours = (text[index - 1] if index > 0 else "", text[index + 1] if index + 1 < len(text) else "")
    return any(char.isalpha() and char.isupper() for char in neighbours)


def cyrillic_to_latin(text: str, normalize_apostrophes: bool = True) -> str:
    """Transliterate Uzbek/Russian Cyrillic to Uzbek Latin; non-Cyrillic text is left unchanged.

    With `normalize_apostrophes`, all apostrophe variants (o‘, gʻ, ʼ) become a plain "'",
    so "o‘qituvchi", "oʻqituvchi" and "o'qituvchi" produce the same token.
    """
    if not isinstance(text, str):
        return text
    result = []
    for index, char in enumerate(text):
        lower = char.lower()
        previous = text[index - 1] if index > 0 else ""
        if lower == "е":
            # "ye" at word start or after a vowel/hard/soft sign: ер -> yer, поезд -> poyezd
            latin = "ye" if not previous.isalpha() or previous in VOWELS or previous.lower() in "ъь" else "e"
        elif lower == "ц":
            # "ts" after a vowel, "s" otherwise: милиция -> militsiya, цех -> sex
            latin = "ts" if previous in VOWELS else "s"
        elif lower in CYRILLIC_TO_LATIN:
            latin = CYRILLIC_TO_LATIN[lower]
        else:
            result.append(char)
            continue
        if char.isupper():
            latin = latin.upper() if _is_upper_word(text, index) else latin.capitalize()
        result.append(latin)
    latin_text = "".join(result)
    return APOSTROPHES.sub("'", latin_text) if normalize_apostrophes else latin_text


def transliterate(X):
    """Apply `cyrillic_to_latin` to every cell of a Series, DataFrame, or array (for FunctionTransformer)."""
    if isinstance(X, pd.DataFrame):
        return X.apply(lambda column: column.map(cyrillic_to_latin))
    if isinstance(X, pd.Series):
        return X.map(cyrillic_to_latin)
    return np.vectorize(cyrillic_to_latin, otypes=[object])(np.asarray(X, dtype=object))


def cyrillic_to_latin_transformer() -> FunctionTransformer:
    """Stateless transformer for ColumnTransformer / Pipeline steps."""
    return FunctionTransformer(transliterate, feature_names_out="one-to-one")
