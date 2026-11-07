from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import Span, Status, StatusCode, Tracer
from sqlalchemy.engine import Engine

from app.config import Settings
from app.telemetry_privacy import PrivacySpanExporter

ServiceName = Literal["gwengift-api", "gwengift-worker"]


@dataclass
class TelemetryRuntime:
    service_name: ServiceName
    provider: TracerProvider
    processor: BatchSpanProcessor
    tracer: Tracer
    fastapi_instrumented: bool = False
    fastapi_app: FastAPI | None = None
    dependencies_instrumented: bool = False


_runtime: TelemetryRuntime | None = None


def configure_tracing(
    settings: Settings,
    service_name: ServiceName,
    *,
    exporter: SpanExporter | None = None,
) -> TelemetryRuntime | None:
    global _runtime

    if not settings.tracing_enabled:
        return None
    if _runtime is not None:
        if _runtime.service_name != service_name:
            raise RuntimeError("Tracing is already configured for another service")
        return _runtime

    endpoint = settings.otel_exporter_otlp_traces_endpoint
    if endpoint is None and exporter is None:
        raise RuntimeError("An OTLP traces endpoint is required")
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": settings.tracing_service_namespace,
            "deployment.environment.name": settings.environment,
        }
    )
    provider = TracerProvider(resource=resource)
    actual_exporter = (
        OTLPSpanExporter(endpoint=endpoint, timeout=2) if exporter is None else exporter
    )
    processor = BatchSpanProcessor(
        PrivacySpanExporter(actual_exporter),
        max_queue_size=512,
        max_export_batch_size=128,
        schedule_delay_millis=100,
        export_timeout_millis=2_000,
    )
    provider.add_span_processor(processor)
    _runtime = TelemetryRuntime(
        service_name=service_name,
        provider=provider,
        processor=processor,
        tracer=provider.get_tracer("gwengift.application"),
    )
    return _runtime


def _instrument_dependencies(runtime: TelemetryRuntime, engine: Engine) -> None:
    if runtime.dependencies_instrumented:
        return
    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        tracer_provider=runtime.provider,
        enable_commenter=False,
    )
    HTTPXClientInstrumentor().instrument(tracer_provider=runtime.provider)
    runtime.dependencies_instrumented = True


def instrument_application(
    app: FastAPI,
    *,
    engine: Engine,
    settings: Settings,
    exporter: SpanExporter | None = None,
) -> TelemetryRuntime | None:
    runtime = configure_tracing(settings, "gwengift-api", exporter=exporter)
    if runtime is None:
        return None
    try:
        if not runtime.fastapi_instrumented:
            runtime.fastapi_app = app
            FastAPIInstrumentor.instrument_app(
                app,
                tracer_provider=runtime.provider,
                excluded_urls="/api/health",
            )
            if app.middleware_stack is not None:
                app.middleware_stack = app.build_middleware_stack()
            runtime.fastapi_instrumented = True
        _instrument_dependencies(runtime, engine)
    except Exception:
        pass
    return runtime


def instrument_worker(
    *,
    engine: Engine,
    settings: Settings,
    exporter: SpanExporter | None = None,
) -> TelemetryRuntime | None:
    runtime = configure_tracing(settings, "gwengift-worker", exporter=exporter)
    if runtime is not None:
        try:
            _instrument_dependencies(runtime, engine)
        except Exception:
            pass
    return runtime


@contextmanager
def operation_span(
    name: str,
    *,
    attributes: Mapping[str, str | int] | None = None,
) -> Iterator[Span | None]:
    runtime = _runtime
    if runtime is None:
        yield None
        return
    try:
        manager = runtime.tracer.start_as_current_span(name, attributes=attributes)
        span = manager.__enter__()
    except Exception:
        try:
            if "manager" in locals():
                manager.__exit__(None, None, None)
        except Exception:
            pass
    else:
        try:
            yield span
        except Exception as exc:
            set_operation_attribute(span, "error.type", type(exc).__name__)
            try:
                span.set_status(Status(StatusCode.ERROR))
            except Exception:
                pass
            try:
                manager.__exit__(type(exc), exc, exc.__traceback__)
            except Exception:
                pass
            raise
        else:
            try:
                manager.__exit__(None, None, None)
            except Exception:
                pass
        return
    yield None


def set_operation_attribute(span: Span | None, key: str, value: str | int) -> None:
    if span is None:
        return
    try:
        span.set_attribute(key, value)
    except Exception:
        pass


def get_telemetry_runtime() -> TelemetryRuntime | None:
    return _runtime


def shutdown_tracing() -> None:
    global _runtime

    if _runtime is None:
        return
    runtime = _runtime
    _runtime = None
    if runtime.fastapi_app is not None:
        try:
            FastAPIInstrumentor.uninstrument_app(runtime.fastapi_app)
        except Exception:
            pass
    try:
        SQLAlchemyInstrumentor().uninstrument()
    except Exception:
        pass
    try:
        HTTPXClientInstrumentor().uninstrument()
    except Exception:
        pass
    try:
        runtime.provider.shutdown()
    except Exception:
        pass
