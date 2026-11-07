# Tracing and telemetry privacy

Tracing is optional and disabled by default. When enabled, the API and worker export operational spans over OTLP/HTTP; tracing never participates in draw selection, debit/award transactions, or retry decisions.

## Privacy boundary

Exported span and resource attributes are filtered through an allowlist before they reach Jaeger or another OTLP collector. Permitted data is limited to service/environment identity, HTTP route/method/status, sanitized outbound URL, database system/operation, error category, and the operational identifiers `gwengift.bet_id`, `gwengift.round_id`, `gwengift.collection_id`, `gwengift.drand_round`, `gwengift.operation`, and `gwengift.outcome`.

The exporter removes all other attributes, strips URL userinfo/query/fragment data, drops span events and status descriptions, and applies the same attribute allowlist to links. This prevents request/response bodies, exception messages, SQL statements and bind values, Telegram `initData`, bot tokens, authorization and development identity headers, Telegram user IDs/usernames, hidden gift identities/manifests, and undisclosed valuation internals from leaving the process in traces.

API and worker traces are correlated by bet and round identifiers, not by Telegram identity. Trace IDs are operational random identifiers and are not evidence used by the draw protocol.

## Local Jaeger stack

Start the normal development stack with the tracing override:

```bash
docker compose -f compose.yaml -f compose.tracing.yaml up --build
```

Open Jaeger at http://127.0.0.1:16686. Select `gwengift-api` or `gwengift-worker`, then use tags such as `gwengift.bet_id=<bet-id>`, `gwengift.round_id=<round-id>`, or `gwengift.outcome=COMPLETED` to correlate the API-created attempt with later worker resolution. These are separate traces joined by searchable identifiers, not one distributed trace with persisted trace context.

The override uses a pinned Jaeger all-in-one image, Badger persistence in `gwengift-jaeger-data`, and an internal OTLP/HTTP endpoint on port 4318. Only the UI/query API is published, on loopback port 16686. The base Compose file and single-container image keep tracing disabled.

Verify real export and worker correlation with the self-cleaning smoke test:

```bash
scripts/smoke-tracing.sh
```

The script uses an isolated Compose project, resolves one real quicknet-backed demo bet, checks API/worker/database/drand spans through Jaeger's query API, and removes only that project's containers, network, and volumes.

## Production configuration

Provide an operator-controlled OTLP/HTTP traces endpoint; the production Compose file deliberately does not start a public Jaeger instance:

```bash
GWENGIFT_TRACING_ENABLED=true \
GWENGIFT_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://collector.example/v1/traces \
GWENGIFT_TRACING_SERVICE_NAMESPACE=gwengift \
docker compose -f compose.production.yaml up --build -d
```

Use a private, authenticated collector or an appropriate TLS/authentication proxy. Protect trace access and retention as operational data. Invalid enabled-tracing configuration fails at startup; runtime collector failures drop or buffer telemetry within bounded limits without changing application results.

To roll back, unset `GWENGIFT_TRACING_ENABLED` or remove `compose.tracing.yaml` from the local command. No application database migration is involved. Jaeger telemetry storage is independent of SQLite bets, inventory, and disclosures.

## Operational limitations

Telemetry is diagnostic data, not an audit log: bounded exporters may drop spans under load or collector outages. Audit disclosures and immutable ledger records remain the source of truth. Anyone with access to a tracing backend can see the exported operational metadata, so production collectors still require appropriate access control and retention policies.
