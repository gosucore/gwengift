import pytest
from pydantic import ValidationError

from app.config import Settings


def test_development_defaults_are_safe() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.dev_identity_enabled is False
    assert settings.telegram_bot_token is None
    assert settings.tracing_enabled is False
    assert settings.otel_exporter_otlp_traces_endpoint is None
    assert settings.tracing_service_namespace == "gwengift"


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


@pytest.mark.parametrize(
    "endpoint",
    [
        None,
        "file:///tmp/traces",
        "http://:4318/v1/traces",
        "http://jaeger:not-a-port/v1/traces",
        "http://jaeger:99999/v1/traces",
    ],
)
def test_tracing_requires_valid_otlp_endpoint(endpoint: str | None) -> None:
    with pytest.raises(ValidationError, match="OTLP traces endpoint"):
        Settings(
            _env_file=None,
            tracing_enabled=True,
            otel_exporter_otlp_traces_endpoint=endpoint,
        )


def test_tracing_accepts_http_and_https_otlp_endpoints() -> None:
    for scheme in ("http", "https"):
        settings = Settings(
            _env_file=None,
            tracing_enabled=True,
            otel_exporter_otlp_traces_endpoint=f"{scheme}://jaeger:4318/v1/traces",
        )
        assert settings.tracing_enabled is True
        assert settings.otel_exporter_otlp_traces_endpoint == (f"{scheme}://jaeger:4318/v1/traces")


def test_production_supports_explicit_tracing() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        telegram_bot_token="test-only-token",
        tracing_enabled=True,
        otel_exporter_otlp_traces_endpoint="https://collector.example/v1/traces",
        tracing_service_namespace="gwengift-production",
    )

    assert settings.tracing_enabled is True
    assert settings.tracing_service_namespace == "gwengift-production"
