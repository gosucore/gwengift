# Proposal

## Why

The API, background worker, database, and drand relays currently have no distributed tracing, making latency, failures, and cross-process draw recovery difficult to diagnose. Adding OpenTelemetry tracing with a Jaeger viewer will make the complete request and draw lifecycle observable without changing gameplay or fairness behavior.

## What Changes

- Add optional, disabled-by-default OpenTelemetry tracing for FastAPI requests, SQLAlchemy database calls, outbound HTTP/drand requests, and background worker passes.
- Export traces over OTLP to a configurable endpoint and service namespace, with consistent resource attributes and trace correlation between API-created attempts and later worker resolution.
- Add an optional Jaeger service to local Docker Compose so developers can inspect traces without sending application data to a third party.
- Document production OTLP configuration, local startup, trace inspection, and verification of tracing-disabled behavior.
- Prevent Telegram launch credentials, bot tokens, hidden pool manifests, full valuation internals, user identity data, and other sensitive payloads from being captured in spans.
- Ensure tracing configuration, exporter outages, or instrumentation failures never change draw outcomes, block gameplay, or introduce a randomness fallback.

## Capabilities

### New Capabilities

- `application-tracing`: Optional distributed tracing, Jaeger inspection, lifecycle correlation, exporter resilience, and telemetry privacy controls for the API and worker.

### Modified Capabilities

None. Existing gameplay, economics, and fairness requirements remain unchanged.

## Impact

- Backend configuration and startup for FastAPI and the worker; SQLAlchemy and outbound HTTP instrumentation.
- New OpenTelemetry API/SDK and instrumentation dependencies, plus a local Jaeger container and persistent development trace storage.
- Docker Compose environment wiring, backend environment examples, README, and tracing verification documentation.
- Backend unit/integration tests and container smoke checks for disabled tracing, trace export, worker correlation, exporter failure, and sensitive-data redaction.
- No public gameplay API schema changes and no frontend browser tracing in this change.
