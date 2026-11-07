import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from app.auth import (
    IdentityValidationError,
    resolve_identity,
    validate_development_identity,
    validate_telegram_init_data,
)
from app.config import Settings

BOT_TOKEN = "123456789:test-only-token"
NOW = 1_800_000_000


def signed_init_data(fields: dict[str, str]) -> str:
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def valid_init_data() -> str:
    return signed_init_data(
        {
            "auth_date": str(NOW - 30),
            "query_id": "AA-test-query",
            "user": json.dumps(
                {"id": 424242, "username": "demo_user", "first_name": "Demo"},
                separators=(",", ":"),
            ),
        }
    )


def test_valid_telegram_launch_data() -> None:
    identity = validate_telegram_init_data(valid_init_data(), BOT_TOKEN, now=NOW)

    assert identity.telegram_user_id == 424242
    assert identity.username == "demo_user"
    assert identity.development is False


def test_optional_third_party_signature_is_not_in_bot_hmac() -> None:
    fields = {
        "auth_date": str(NOW),
        "user": json.dumps({"id": 42}, separators=(",", ":")),
        "signature": "third-party-signature",
    }
    fields_without_signature = {key: value for key, value in fields.items() if key != "signature"}
    check_string = "\n".join(
        f"{key}={fields_without_signature[key]}" for key in sorted(fields_without_signature)
    )
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()

    identity = validate_telegram_init_data(urlencode(fields), BOT_TOKEN, now=NOW)
    assert identity.telegram_user_id == 42


def test_invalid_hash_is_rejected() -> None:
    with pytest.raises(IdentityValidationError, match="authentication failed"):
        validate_telegram_init_data(valid_init_data()[:-1] + "0", BOT_TOKEN, now=NOW)


def test_expired_launch_data_is_rejected() -> None:
    with pytest.raises(IdentityValidationError, match="expired"):
        validate_telegram_init_data(valid_init_data(), BOT_TOKEN, max_age_seconds=10, now=NOW)


def test_future_launch_data_is_rejected() -> None:
    init_data = signed_init_data({"auth_date": str(NOW + 120), "user": '{"id":42}'})
    with pytest.raises(IdentityValidationError, match="future"):
        validate_telegram_init_data(init_data, BOT_TOKEN, now=NOW)


def test_spoofed_user_is_rejected() -> None:
    original = json.dumps({"id": 424242, "username": "demo_user"}, separators=(",", ":"))
    spoofed = json.dumps({"id": 1, "username": "attacker"}, separators=(",", ":"))
    init_data = signed_init_data({"auth_date": str(NOW), "user": original})
    tampered = init_data.replace(urlencode({"user": original}), urlencode({"user": spoofed}))

    with pytest.raises(IdentityValidationError, match="authentication failed"):
        validate_telegram_init_data(tampered, BOT_TOKEN, now=NOW)


@pytest.mark.parametrize(
    "init_data",
    ["", "not-a-query", "auth_date=1&auth_date=2&user=%7B%7D&hash=abc"],
)
def test_malformed_or_duplicate_launch_data_is_rejected(init_data: str) -> None:
    with pytest.raises(IdentityValidationError):
        validate_telegram_init_data(init_data, BOT_TOKEN, now=NOW)


def test_explicit_development_identity_adapter() -> None:
    settings = Settings(_env_file=None, dev_identity_enabled=True)

    identity = validate_development_identity(777, "local", settings)

    assert identity.telegram_user_id == 777
    assert identity.development is True


def test_development_identity_is_disabled_by_default() -> None:
    with pytest.raises(IdentityValidationError, match="not enabled"):
        validate_development_identity(777, None, Settings(_env_file=None))


def test_invalid_launch_data_never_falls_back_to_development_identity() -> None:
    settings = Settings(
        _env_file=None,
        telegram_bot_token=BOT_TOKEN,
        dev_identity_enabled=True,
    )

    with pytest.raises(IdentityValidationError):
        resolve_identity(
            init_data="invalid",
            settings=settings,
            development_user_id=777,
            now=NOW,
        )


def test_missing_launch_data_requires_explicit_adapter_or_telegram() -> None:
    with pytest.raises(IdentityValidationError, match="opened through Telegram"):
        resolve_identity(init_data=None, settings=Settings(_env_file=None))

    identity = resolve_identity(
        init_data=None,
        settings=Settings(_env_file=None, dev_identity_enabled=True),
        development_user_id=99,
    )
    assert identity.telegram_user_id == 99
