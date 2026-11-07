import pytest
from pydantic import ValidationError

from app.config import Settings


def test_development_defaults_are_safe() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.dev_identity_enabled is False
    assert settings.telegram_bot_token is None


def test_production_requires_telegram_bot_token() -> None:
    with pytest.raises(ValidationError, match="TELEGRAM_BOT_TOKEN"):
        Settings(_env_file=None, environment="production")


def test_production_rejects_development_identity() -> None:
    with pytest.raises(ValidationError, match="Development identity"):
        Settings(
            _env_file=None,
            environment="production",
            telegram_bot_token="test-only-token",
            dev_identity_enabled=True,
        )
