# Design

## Context

See `proposal.md` — Why. One production container runs separate Uvicorn and worker processes over the same SQLite database. The worker resolves attempts through synchronous HTTPX drand calls, while development Compose starts separate backend and frontend services. No tracing SDK, collector, or telemetry storage currently exists. See `specs/application-tracing/spec.md` for the required behavior and privacy boundary.

## Goals / Non-Goals

**Goals:**

- Initialize the same optional telemetry pipeline in API and worker processes with process-specific resource identities.
- Provide automatic boundary spans and focused manual spans for draw and disclosure operations.
- Make API-created attempts searchable alongside their later worker traces without changing domain persistence.
- Provide a reproducible local Jaeger stack and verify actual OTLP export.

**Non-Goals:**

- Browser/RUM instrumentation, metrics pipelines, log migration, or replacing existing application logging.
- Persisting trace context in bets or forcing API and asynchronous worker work into one distributed trace.
- Deploying or publicly exposing Jaeger in production; production exports to an operator-provided OTLP destination.
- Capturing business payloads for debugging or changing gameplay APIs, database schemas, or draw algorithms.

## Decisions

### 1. Use OpenTelemetry SDK with OTLP/HTTP protobuf export

Add the OpenTelemetry SDK, OTLP/HTTP exporter, and FastAPI, SQLAlchemy, and HTTPX instrumentors as backend runtime dependencies. Centralize setup in one telemetry module and invoke it explicitly from API and worker startup only when `GWENGIFT_TRACING_ENABLED=true`.

Use a configurable traces endpoint, default service namespace `gwengift`, environment resource metadata, and service names `gwengift-api` and `gwengift-worker`. OTLP/HTTP exports to Jaeger's port `4318` `/v1/traces` endpoint and avoids adding a gRPC client stack. OTLP/gRPC and vendor-specific exporters are unnecessary alternatives for this change.

Validate the endpoint when tracing is enabled. Runtime collector errors remain isolated from application work; an invalid startup configuration may fail fast rather than silently misdirecting telemetry.

### 2. Instrument process boundaries once and add narrow domain spans

Instrument the FastAPI app, SQLAlchemy engine, and HTTPX client calls once per process, avoiding duplicate registration under Uvicorn reload and tests. Exclude health checks from routine trace volume. Do not enable request/response body, header, or SQL bind-parameter capture.

Add manual spans around worker passes and individual bet/disclosure operations. Attach only allowlisted fields such as `gwengift.bet_id`, `gwengift.round_id`, `gwengift.collection_id`, operation name, outcome category, and drand round number. Never attach gift identity before disclosure, user identity, credentials, manifests, valuation payloads, or exception messages that may contain them.

Use normal parent-child context within each process. Across API and worker processes, correlate separate traces through the shared bet/round identifiers rather than adding trace columns to the immutable bet schema. Span links backed by new persisted trace state were rejected as disproportionate and more invasive.

### 3. Isolate exporters from application correctness

Use a bounded `BatchSpanProcessor` with finite queue, batch, and export timeouts. Telemetry code must not wrap domain calls in ways that replace or swallow their exceptions; it records the existing outcome and re-raises application errors. No randomness or retry decision may depend on telemetry state.

Unit tests use an in-memory exporter and deterministic protocol fixtures. They assert equivalent enabled/disabled behavior, expected span hierarchy and correlation attributes, failure recording, and absence of sensitive values across all exported span data.

### 4. Provide Jaeger through a separate development Compose override

Add `compose.tracing.yaml` that enables backend tracing, sets its OTLP endpoint to `http://jaeger:4318/v1/traces`, and starts a pinned Jaeger all-in-one image. Configure Badger persistence on a dedicated telemetry volume, keep the OTLP collector ports internal to the Compose network, and bind the Jaeger UI and query API only to `127.0.0.1:16686`; do not add Jaeger to `compose.production.yaml`.

The normal development and single-container application remain tracing-disabled. The documented tracing command combines the base and tracing override files. A self-cleaning tracing smoke script will start that stack, generate API and worker activity, poll Jaeger's query API for the expected service and correlation attributes, and remove only its own resources.

### 5. Make rollout and rollback independent of application data

No application database migration is required. Deploy with tracing disabled, then enable it only after configuring a reachable OTLP endpoint. Rollback is to unset tracing or remove the tracing override; application state and audit evidence remain untouched. Jaeger's volume contains telemetry only and can be retained or deleted independently.

## Risks / Trade-offs

- [Automatic instrumentation captures unexpected data after an upgrade] → Pin supported dependency ranges, disable payload/header/SQL-value capture, use allowlisted custom attributes, and run recursive exported-span privacy tests.
- [Collector outage consumes memory or delays shutdown] → Bound queues and export times, drop excess telemetry, and test unavailable-collector behavior.
- [Reloads or repeated initialization create duplicate spans] → Make setup idempotent per process and cover repeated setup in tests.
- [Separate API and worker traces are less convenient than one trace] → Standardize searchable bet/round attributes and document Jaeger filtering; avoid domain-schema changes.
- [Jaeger exposes sensitive operational metadata] → Loopback-only local binding, no production viewer, and documented access expectations for any external OTLP collector.
- [Tracing adds dependencies and modest runtime overhead] → Keep it opt-in, exclude health checks, and run the complete existing quality and container suites in both modes where practical.
