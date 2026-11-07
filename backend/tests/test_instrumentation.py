import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config import Settings
from app.services.drand import QUICKNET
from app.services.drand_adapter import DrandAdapter
from app.telemetry import instrument_application, shutdown_tracing


def enabled_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        tracing_enabled=True,
        otel_exporter_otlp_traces_endpoint="http://jaeger:4318/v1/traces",
    )


def first_attribute(span: ReadableSpan, *names: str) -> object:
    for name in names:
        value = span.attributes.get(name) if span.attributes is not None else None
        if value is not None:
            return value
    raise AssertionError(f"None of {names} found in {span.attributes}")


@pytest.fixture
def clean_instrumentation() -> Iterator[None]:
    yield
    SQLAlchemyInstrumentor().uninstrument()
    HTTPXClientInstrumentor().uninstrument()
    shutdown_tracing()


@pytest.fixture
def drand_server() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            payload = json.dumps(
                {
                    "public_key": QUICKNET.public_key,
                    "period": QUICKNET.period_seconds,
                    "genesis_time": QUICKNET.genesis_time,
                    "hash": QUICKNET.chain_hash,
                    "schemeID": QUICKNET.scheme,
                    "metadata": {"beaconID": QUICKNET.beacon_id},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def test_api_database_and_drand_spans_without_duplicates(
    database_engine: Engine,
    clean_instrumentation: None,
    drand_server: str,
) -> None:
    exporter = InMemorySpanExporter()
    test_app = FastAPI()

    @test_app.get("/api/test/{item_id}")
    def test_route(item_id: str) -> dict[str, str]:
        with database_engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
        adapter = DrandAdapter(relays=(drand_server,))
        adapter.fetch_network_metadata()
        return {"item_id": item_id}

    @test_app.get("/api/error")
    def error_route() -> None:
        raise RuntimeError("safe-test-error")

    @test_app.get("/api/health")
    def health_route() -> dict[str, str]:
        return {"status": "ok"}

    instrument_application(
        test_app,
        engine=database_engine,
        settings=enabled_settings(),
        exporter=exporter,
    )
    instrument_application(
        test_app,
        engine=database_engine,
        settings=enabled_settings(),
        exporter=exporter,
    )
    client = TestClient(test_app, raise_server_exceptions=False)
    assert client.get("/api/test/example").status_code == 200
    assert client.get("/api/error").status_code == 500
    assert client.get("/api/health").status_code == 200
    shutdown_tracing()
    FastAPIInstrumentor.uninstrument_app(test_app)

    spans = exporter.get_finished_spans()
    server_spans = [span for span in spans if span.kind == SpanKind.SERVER]
    assert len(server_spans) == 2
    success = next(
        span
        for span in server_spans
        if first_attribute(span, "http.route") == "/api/test/{item_id}"
    )
    assert first_attribute(success, "http.request.method", "http.method") == "GET"
    assert first_attribute(success, "http.response.status_code", "http.status_code") == 200
    assert (
        success.start_time is not None
        and success.end_time is not None
        and success.start_time < success.end_time
    )
    error = next(
        span for span in server_spans if first_attribute(span, "http.route") == "/api/error"
    )
    assert first_attribute(error, "http.response.status_code", "http.status_code") == 500
    assert any(span.kind == SpanKind.CLIENT and "SELECT" in span.name for span in spans), [
        (span.name, span.kind) for span in spans
    ]
    http_spans = [
        span
        for span in spans
        if span.instrumentation_scope is not None
        and span.instrumentation_scope.name == "opentelemetry.instrumentation.httpx"
    ]
    assert len(http_spans) == 1
    assert str(first_attribute(http_spans[0], "url.full", "http.url")).endswith(
        f"/{QUICKNET.chain_hash}/info"
    )
