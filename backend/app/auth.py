import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

from app.config import Settings


class IdentityValidationError(ValueError):
    """Raised when launch credentials cannot authenticate a user."""


@dataclass(frozen=True)
class TelegramIdentity:
    telegram_user_id: int
    username: str | None
    development: bool = False


def _data_check_string(fields: dict[str, str]) -> str:
    return "\n".join(f"{key}={fields[key]}" for key in sorted(fields))


def _telegram_hash(fields: dict[str, str], bot_token: str) -> str:
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(
        secret,
        _data_check_string(fields).encode(),
        hashlib.sha256,
    ).hexdigest()


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = 300,
    now: int | None = None,
) -> TelegramIdentity:
    if not init_data or not bot_token or max_age_seconds <= 0:
        raise IdentityValidationError("Telegram launch data is invalid")

    try:
        pairs = parse_qsl(
            init_data,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=100,
        )
    except ValueError as exc:
        raise IdentityValidationError("Telegram launch data is malformed") from exc

    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise IdentityValidationError("Telegram launch data contains duplicate fields")

    supplied_hash = fields.pop("hash", None)
    # Telegram's optional third-party Ed25519 signature is not part of bot-token HMAC.
    fields.pop("signature", None)
    if not supplied_hash or len(supplied_hash) != 64:
        raise IdentityValidationError("Telegram launch data hash is missing")

    expected_hash = _telegram_hash(fields, bot_token)
    if not hmac.compare_digest(expected_hash, supplied_hash.lower()):
        raise IdentityValidationError("Telegram launch data authentication failed")

    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, ValueError) as exc:
        raise IdentityValidationError("Telegram launch date is missing or invalid") from exc

    current_timestamp = int(time.time()) if now is None else now
    age = current_timestamp - auth_date
    if age > max_age_seconds or age < -60:
        raise IdentityValidationError("Telegram launch data is expired or from the future")

    try:
        user: Any = json.loads(fields["user"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise IdentityValidationError("Telegram user data is missing or invalid") from exc

    if not isinstance(user, dict):
        raise IdentityValidationError("Telegram user data is invalid")
    telegram_user_id = user.get("id")
    username = user.get("username")
    if (
        not isinstance(telegram_user_id, int)
        or isinstance(telegram_user_id, bool)
        or telegram_user_id <= 0
        or (username is not None and not isinstance(username, str))
    ):
        raise IdentityValidationError("Telegram user identity is invalid")

    return TelegramIdentity(telegram_user_id=telegram_user_id, username=username)


def validate_development_identity(
    telegram_user_id: int,
    username: str | None,
    settings: Settings,
) -> TelegramIdentity:
    if settings.environment not in ("development", "test") or not settings.dev_identity_enabled:
        raise IdentityValidationError("Development identity is not enabled")
    if telegram_user_id <= 0:
        raise IdentityValidationError("Development user identity is invalid")
    return TelegramIdentity(
        telegram_user_id=telegram_user_id,
        username=username,
        development=True,
    )


def resolve_identity(
    *,
    init_data: str | None,
    settings: Settings,
    development_user_id: int | None = None,
    development_username: str | None = None,
    now: int | None = None,
) -> TelegramIdentity:
    if init_data is not None:
        token = settings.telegram_bot_token
        if token is None or not token.get_secret_value():
            raise IdentityValidationError("Telegram authentication is not configured")
        return validate_telegram_init_data(
            init_data,
            token.get_secret_value(),
            max_age_seconds=settings.init_data_max_age_seconds,
            now=now,
        )

    if development_user_id is not None:
        return validate_development_identity(
            development_user_id,
            development_username,
            settings,
        )
    raise IdentityValidationError("The app must be opened through Telegram")
