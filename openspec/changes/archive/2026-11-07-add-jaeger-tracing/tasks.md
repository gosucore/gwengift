# Tasks

## 1. Telemetry configuration and SDK

- [x] 1.1 Add the selected OpenTelemetry SDK, OTLP/HTTP exporter, and FastAPI/SQLAlchemy/HTTPX instrumentation dependencies plus tracing settings and environment examples; verify installation and configuration tests cover safe disabled defaults, enabled endpoint validation, service metadata, and production settings.
- [x] 1.2 Implement idempotent per-process telemetry setup with bounded batch export and API/worker resource identities; verify in-memory exporter tests cover disabled setup, repeated initialization, explicit shutdown, and expected resource attributes.

## 2. API instrumentation and privacy

- [x] 2.1 Instrument FastAPI, SQLAlchemy, and outbound HTTPX/drand operations without payload capture and exclude routine health checks; verify API integration tests show route, method, status/error, duration, database, and drand dependency spans without duplicate spans.
- [x] 2.2 Enforce allowlisted operational attributes and document the telemetry privacy boundary in `docs/tracing.md`; verify recursive exported-span tests reject Telegram credentials and identities, development identity headers, request/response bodies, SQL values, hidden gift identities/manifests, and undisclosed valuation internals.

## 3. Worker lifecycle and failure isolation

- [x] 3.1 Add allowlisted bet-creation, worker-pass, recovery, resolution, cancellation, and disclosure spans with shared bet/round identifiers and safe error categorization; verify deterministic API/worker tests can correlate the same attempt and failed operations retain their existing retry semantics.
- [x] 3.2 Isolate exporter and instrumentation failures from domain processing; verify collector-outage and enabled-versus-disabled tests preserve responses, commits, ledger/gift invariants, worker retries, protocol outcomes, and the prohibition on substitute randomness.

## 4. Jaeger stack and live verification

- [x] 4.1 Add a pinned Jaeger service, persistent telemetry volume, loopback-only UI, and backend OTLP wiring in `compose.tracing.yaml`; document local startup, Jaeger filtering, production OTLP deployment, limitations, and rollback in README and `docs/tracing.md`, and verify Compose configuration and default non-tracing startup.
- [x] 4.2 Add a self-cleaning `scripts/smoke-tracing.sh` that generates real API and worker activity and polls Jaeger for expected API/worker services, dependency spans, and shared correlation identifiers; verify the script passes and cleans up only its own resources.

## 5. Final integration verification

- [x] 5.1 Run the complete backend lint, formatting, strict type-check, unit/protocol/concurrency/integration suites, existing frontend checks, production image build, tracing-disabled restart smoke, and tracing-enabled Jaeger smoke; verify all pass and the documentation matches the executed commands.
