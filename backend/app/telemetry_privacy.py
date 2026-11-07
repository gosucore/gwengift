from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Link, Status

ATTRIBUTE_ALLOWLIST = frozenset(
    {
        "deployment.environment.name",
        "error.type",
        "gwengift.bet_id",
        "gwengift.collection_id",
        "gwengift.drand_round",
        "gwengift.operation",
        "gwengift.outcome",
        "gwengift.round_id",
        "http.method",
        "http.request.method",
        "http.response.status_code",
        "http.route",
        "http.scheme",
        "http.status_code",
        "http.url",
        "network.protocol.version",
        "server.address",
        "server.port",
        "service.name",
        "service.namespace",
        "url.full",
        "db.system",
        "db.operation",
        "db.operation.name",
    }
)
URL_ATTRIBUTES = frozenset({"http.url", "url.full"})
RESOURCE_ATTRIBUTE_ALLOWLIST = frozenset(
    {"service.name", "service.namespace", "deployment.environment.name"}
)


def _without_url_secrets(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return value
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    netloc = f"{host}:{parsed.port}" if parsed.port is not None else host
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _safe_attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    if attributes is None:
        return {}
    return {
        key: _without_url_secrets(value) if key in URL_ATTRIBUTES else value
        for key, value in attributes.items()
        if key in ATTRIBUTE_ALLOWLIST
    }


def _safe_resource(resource: Resource) -> Resource:
    return Resource(
        {
            key: value
            for key, value in resource.attributes.items()
            if key in RESOURCE_ATTRIBUTE_ALLOWLIST
        }
    )


def sanitize_span(span: ReadableSpan) -> ReadableSpan:
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=_safe_resource(span.resource),
        attributes=_safe_attributes(span.attributes),
        events=(),
        links=tuple(
            Link(link.context, attributes=_safe_attributes(link.attributes)) for link in span.links
        ),
        kind=span.kind,
        status=Status(span.status.status_code),
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class PrivacySpanExporter(SpanExporter):
    def __init__(self, delegate: SpanExporter) -> None:
        self.delegate = delegate

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            return self.delegate.export([sanitize_span(span) for span in spans])
        except Exception:
            return SpanExportResult.FAILURE

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        try:
            return self.delegate.force_flush(timeout_millis)
        except Exception:
            return False

    def shutdown(self) -> None:
        try:
            self.delegate.shutdown()
        except Exception:
            pass
