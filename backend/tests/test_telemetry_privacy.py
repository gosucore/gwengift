import json
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Link, SpanContext, Status, StatusCode, TraceFlags
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.auth import TelegramIdentity
from app.config import Settings
from app.services.accounts import get_or_create_account
from app.services.bets import CollectionUnavailableError, create_bet
from app.telemetry import configure_tracing, instrument_application, shutdown_tracing
from app.telemetry_privacy import PrivacySpanExporter

SECRETS = (
    "telegram-init-data-secret",
    "telegram-bot-token-secret",
    "development-user-header-secret",
    "424242",
    "hidden-gift-uuid-secret",
    "canonical-hidden-manifest-secret",
    "undisclosed-valuation-secret",
    "request-response-body-secret",
    "sql-bind-value-secret",
    "client-supplied-collection-secret",
)


@pytest.fixture
def clean_instrumentation() -> Iterator[None]:
    yield
    SQLAlchemyInstrumentor().uninstrument()
    HTTPXClientInstrumentor().uninstrument()
    shutdown_tracing()


def assert_no_sensitive_values(exporter: InMemorySpanExporter) -> None:
    serialized = json.dumps([json.loads(span.to_json()) for span in exporter.get_finished_spans()])
    for secret in SECRETS:
        assert secret not in serialized


def test_export_allowlist_removes_sensitive_attributes_events_links_and_resources() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(
        resource=Resource.create(
            {"service.name": "gwengift-api", "private.resource": "telegram-bot-token-secret"}
        )
    )
    provider.add_span_processor(SimpleSpanProcessor(PrivacySpanExporter(exporter)))
    tracer = provider.get_tracer("privacy-test")
    link_context = SpanContext(
        trace_id=1,
        span_id=2,
        is_remote=True,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )

    with tracer.start_as_current_span(
        "draw.resolve",
        attributes={
            "gwengift.bet_id": "safe-bet-id",
            "http.request.header.x_telegram_init_data": "telegram-init-data-secret",
            "enduser.id": "424242",
        },
        links=[Link(link_context, attributes={"manifest": "canonical-hidden-manifest-secret"})],
    ) as span:
        span.add_event("exception", {"exception.message": "undisclosed-valuation-secret"})
        span.set_status(Status(StatusCode.ERROR, "sql-bind-value-secret"))
    provider.shutdown()

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    exported = spans[0]
    assert exported.attributes == {"gwengift.bet_id": "safe-bet-id"}
    assert exported.events == ()
    assert exported.status.description is None
    assert exported.links[0].attributes == {}
    assert set(exported.resource.attributes) == {"service.name"}
    assert_no_sensitive_values(exporter)


def test_instrumented_sensitive_request_is_sanitized_before_export(
    database_engine: Engine,
    clean_instrumentation: None,
) -> None:
    exporter = InMemorySpanExporter()
    test_app = FastAPI()

    @test_app.post("/api/private")
    def private_route() -> None:
        with database_engine.connect() as connection:
            connection.execute(text("SELECT :value"), {"value": "sql-bind-value-secret"})
        raise RuntimeError("request-response-body-secret")

    settings = Settings(
        _env_file=None,
        environment="test",
        tracing_enabled=True,
        otel_exporter_otlp_traces_endpoint="http://jaeger:4318/v1/traces",
    )
    instrument_application(test_app, engine=database_engine, settings=settings, exporter=exporter)
    client = TestClient(test_app, raise_server_exceptions=False)
    response = client.post(
        "/api/private?initData=telegram-init-data-secret",
        content="request-response-body-secret",
        headers={
            "X-Telegram-Init-Data": "telegram-init-data-secret",
            "X-Dev-Telegram-User-Id": "424242",
            "X-Dev-Username": "development-user-header-secret",
            "Authorization": "telegram-bot-token-secret",
        },
    )
    assert response.status_code == 500
    shutdown_tracing()
    FastAPIInstrumentor.uninstrument_app(test_app)

    assert exporter.get_finished_spans()
    assert_no_sensitive_values(exporter)
    assert all(not span.events for span in exporter.get_finished_spans())


def test_rejected_client_collection_id_is_not_exported(db_session: Session) -> None:
    user = get_or_create_account(
        db_session,
        TelegramIdentity(telegram_user_id=1001, username="privacy-test"),
        10_000,
    )
    exporter = InMemorySpanExporter()
    configure_tracing(
        Settings(
            _env_file=None,
            environment="test",
            tracing_enabled=True,
            otel_exporter_otlp_traces_endpoint="http://jaeger:4318/v1/traces",
        ),
        "gwengift-api",
        exporter=exporter,
    )

    with pytest.raises(CollectionUnavailableError):
        create_bet(
            db_session,
            user_id=user.id,
            collection_id="client-supplied-collection-secret",
            idempotency_key="privacy-test",
        )
    shutdown_tracing()

    span = next(span for span in exporter.get_finished_spans() if span.name == "bet.create")
    assert span.attributes is not None
    assert "gwengift.collection_id" not in span.attributes
    assert_no_sensitive_values(exporter)
