from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from sqlalchemy.engine import Engine

from app.config import Settings
from app.telemetry import (
    ServiceName,
    configure_tracing,
    get_telemetry_runtime,
    instrument_application,
    instrument_worker,
    shutdown_tracing,
)


@pytest.fixture(autouse=True)
def clean_telemetry_runtime() -> Iterator[None]:
    shutdown_tracing()
    yield
    shutdown_tracing()


def enabled_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        tracing_enabled=True,
        otel_exporter_otlp_traces_endpoint="http://jaeger:4318/v1/traces",
    )


def test_disabled_tracing_does_not_create_runtime() -> None:
    exporter = InMemorySpanExporter()

    runtime = configure_tracing(Settings(_env_file=None), "gwengift-api", exporter=exporter)

    assert runtime is None
    assert get_telemetry_runtime() is None
    assert exporter.get_finished_spans() == ()
    shutdown_tracing()


@pytest.mark.parametrize("service_name", ["gwengift-api", "gwengift-worker"])
def test_enabled_tracing_exports_bounded_spans_with_resource_identity(
    service_name: ServiceName,
) -> None:
    exporter = InMemorySpanExporter()

    runtime = configure_tracing(enabled_settings(), service_name, exporter=exporter)
    assert runtime is not None
    assert isinstance(runtime.processor, BatchSpanProcessor)
    assert configure_tracing(enabled_settings(), service_name, exporter=exporter) is runtime
    with runtime.tracer.start_as_current_span("telemetry.test"):
        pass

    shutdown_tracing()
    shutdown_tracing()

    assert get_telemetry_runtime() is None
    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["telemetry.test"]
    attributes = spans[0].resource.attributes
    assert attributes["service.name"] == service_name
    assert attributes["service.namespace"] == "gwengift"
    assert attributes["deployment.environment.name"] == "test"


def test_runtime_cannot_switch_service_identity() -> None:
    exporter = InMemorySpanExporter()
    assert configure_tracing(enabled_settings(), "gwengift-api", exporter=exporter) is not None

    with pytest.raises(RuntimeError, match="another service"):
        configure_tracing(enabled_settings(), "gwengift-worker", exporter=exporter)


def broken_instrumentor(*args: object, **kwargs: object) -> None:
    raise RuntimeError("instrumentation-unavailable")


@pytest.mark.parametrize(
    "target",
    [
        "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app",
        "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor.instrument",
        "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor.instrument",
    ],
)
def test_automatic_instrumentation_failure_does_not_block_api(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    test_app = FastAPI()

    @test_app.get("/api/test")
    def test_route() -> dict[str, bool]:
        return {"ok": True}

    monkeypatch.setattr(target, broken_instrumentor)
    runtime = instrument_application(
        test_app,
        engine=database_engine,
        settings=enabled_settings(),
        exporter=InMemorySpanExporter(),
    )

    assert runtime is not None
    assert TestClient(test_app).get("/api/test").json() == {"ok": True}


@pytest.mark.parametrize(
    "target",
    [
        "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor.instrument",
        "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor.instrument",
    ],
)
def test_automatic_instrumentation_failure_does_not_block_worker(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    monkeypatch.setattr(target, broken_instrumentor)

    runtime = instrument_worker(
        engine=database_engine,
        settings=enabled_settings(),
        exporter=InMemorySpanExporter(),
    )

    assert runtime is not None


def test_shutdown_allows_automatic_instrumentation_to_be_reconfigured(
    database_engine: Engine,
) -> None:
    test_app = FastAPI()

    @test_app.get("/api/test")
    def test_route() -> dict[str, bool]:
        return {"ok": True}

    exporters = [InMemorySpanExporter(), InMemorySpanExporter()]
    for exporter in exporters:
        assert instrument_application(
            test_app,
            engine=database_engine,
            settings=enabled_settings(),
            exporter=exporter,
        )
        assert TestClient(test_app).get("/api/test").status_code == 200
        shutdown_tracing()

    for exporter in exporters:
        server_spans = [
            span for span in exporter.get_finished_spans() if span.kind == SpanKind.SERVER
        ]
        assert len(server_spans) == 1
