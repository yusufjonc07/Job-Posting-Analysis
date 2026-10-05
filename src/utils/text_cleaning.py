"""Normalize noisy Telegram text and mask personal data before vectorizing or sharing."""

import re
import unicodedata

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from src.utils.transliteration import cyrillic_to_latin

URL_PATTERN = re.compile(r"(?:https?://|www\.|t\.me/)\S+", re.IGNORECASE)
MENTION_PATTERN = re.compile(r"@\w{3,}")
EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
# Korean mobile/landline (010-1234-5678, 01012345678, +82 10 1234 5678, 031-123-4567).
PHONE_PATTERN = re.compile(r"(?:\+?82[\s-]?|\b0)(?:1[016789]|[2-6]\d?)[\s.-]?\d{3,4}[\s.-]?\d{4}\b")
NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)*")
EMOJI_PATTERN = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U00002B00-\U00002BFF"
    "\U0000FE0F\U0000200D\U000020E3]+"
)
REPEATED_PUNCTUATION = re.compile(r"([!?.,+\-=_*~])\1+")
WHITESPACE_PATTERN = re.compile(r"\s+")


def clean_text(
    text: str,
    lowercase: bool = True,
    transliterate: bool = True,
    mask_urls: bool = True,
    mask_mentions: bool = True,
    mask_emails: bool = True,
    mask_phones: bool = True,
    mask_numbers: bool = False,
    remove_emoji: bool = True,
) -> str:
    """Normalize one post. Masks become placeholder tokens (URL, USER, EMAIL, PHONE, NUM).

    Phones are masked before numbers so a phone never turns into several NUM tokens.
    Keep `mask_numbers=False` when salaries or hours matter for the model.
    """
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKC", text)
    if transliterate:
        text = cyrillic_to_latin(text)
    if mask_urls:
        text = URL_PATTERN.sub(" URL ", text)
    if mask_emails:
        text = EMAIL_PATTERN.sub(" EMAIL ", text)
    if mask_mentions:
        text = MENTION_PATTERN.sub(" USER ", text)
    if mask_phones:
        text = PHONE_PATTERN.sub(" PHONE ", text)
    if mask_numbers:
        text = NUMBER_PATTERN.sub(" NUM ", text)
    if remove_emoji:
        text = EMOJI_PATTERN.sub(" ", text)
    text = REPEATED_PUNCTUATION.sub(r"\1", text)
    if lowercase:
        # Keep placeholder tokens upper-case so they never collide with real words.
        text = re.sub(r"\b(?!(?:URL|USER|EMAIL|PHONE|NUM)\b)\w+", lambda match: match.group(0).lower(), text)
    return WHITESPACE_PATTERN.sub(" ", text).strip()


class TextCleaner(BaseEstimator, TransformerMixin):
    """Scikit-learn transformer around `clean_text`; options can be tuned with GridSearchCV."""

    def __init__(
        self,
        lowercase=True,
        transliterate=True,
        mask_urls=True,
        mask_mentions=True,
        mask_emails=True,
        mask_phones=True,
        mask_numbers=False,
        remove_emoji=True,
    ):
        self.lowercase = lowercase
        self.transliterate = transliterate
        self.mask_urls = mask_urls
        self.mask_mentions = mask_mentions
        self.mask_emails = mask_emails
        self.mask_phones = mask_phones
        self.mask_numbers = mask_numbers
        self.remove_emoji = remove_emoji

    def fit(self, X, y=None):
        self.n_features_in_ = 1 if np.ndim(X) == 1 else np.shape(X)[1]
        return self

    def transform(self, X):
        options = self.get_params()
        clean = lambda text: clean_text(text, **options)
        if isinstance(X, pd.DataFrame):
            return X.apply(lambda column: column.map(clean))
        if isinstance(X, pd.Series):
            return X.map(clean)
        return np.vectorize(clean, otypes=[object])(np.asarray(X, dtype=object))

    def get_feature_names_out(self, input_features=None):
        return np.asarray(input_features if input_features is not None else ["text"], dtype=object)
