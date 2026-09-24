"""Authentication settings for a TDLib session."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthSettings:
    """Values needed to authenticate a Telegram user account."""

    phone_number: str
    database_directory: str


def validate_auth_settings(settings: AuthSettings) -> None:
    """Reject incomplete authentication settings before connecting."""
    if not settings.phone_number.strip():
        raise ValueError("TELEGRAM_PHONE_NUMBER must not be empty")
    if not settings.database_directory.strip():
        raise ValueError("TDLIB_DATABASE_DIR must not be empty")
