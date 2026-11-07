# Spec Delta

## Purpose

Provides optional distributed tracing for API requests and background draw processing, with local Jaeger inspection and privacy and failure-isolation guarantees that protect gameplay and fairness behavior.

## ADDED Requirements

### Requirement: Optional tracing activation
The system SHALL disable tracing by default and SHALL enable trace collection and export only through explicit environment configuration.

#### Scenario: Tracing is not configured
- **WHEN** the API or worker starts with default configuration
- **THEN** application behavior remains unchanged and no trace exporter is activated

#### Scenario: Tracing is explicitly enabled
- **WHEN** tracing is enabled with a valid OTLP traces endpoint
- **THEN** the API and worker export tracing data to the configured destination with identifiable service and environment metadata

### Requirement: API and dependency traces
When tracing is enabled, the system SHALL record API request duration and outcome plus database and outbound drand HTTP dependency operations needed to diagnose request processing.

#### Scenario: API request completes
- **WHEN** an instrumented API endpoint handles a request
- **THEN** its trace identifies the route, method, status or error, duration, and relevant database or drand dependency spans

### Requirement: Worker and draw lifecycle traces
When tracing is enabled, the system SHALL trace worker passes and individual recovery, resolution, cancellation, and disclosure operations with searchable non-sensitive attempt and round identifiers.

#### Scenario: Worker resolves an API-created attempt
- **WHEN** the worker processes an attempt created through the API
- **THEN** the API and worker traces carry the same bet identifier and available round identifier so their separate traces can be correlated

#### Scenario: Worker pass fails
- **WHEN** a worker operation raises an error
- **THEN** its span records the failure without changing the persisted retry behavior

### Requirement: Local Jaeger inspection
The development deployment SHALL provide an opt-in Jaeger viewer with persistent local trace storage and SHALL NOT expose that viewer publicly by default.

#### Scenario: Developer starts tracing stack
- **WHEN** a developer starts the documented local tracing configuration
- **THEN** Jaeger receives application traces and the developer can inspect them through a loopback-accessible interface

### Requirement: Telemetry privacy
Traces MUST NOT contain Telegram launch data, bot tokens, development identity headers, Telegram user IDs or usernames, hidden gift identities or manifests, undisclosed valuation internals, request or response bodies, or SQL bind values.

#### Scenario: Sensitive request is traced
- **WHEN** an authenticated request or draw operation produces spans while sensitive values are present
- **THEN** exported spans, events, links, and resource attributes contain only approved operational metadata and none of those sensitive values

### Requirement: Runtime telemetry failure isolation
Tracing exporter and instrumentation failures SHALL NOT fail API operations, alter database commits, stop worker retries, change draw outcomes, or introduce another randomness source.

#### Scenario: Trace collector is unavailable
- **WHEN** the configured collector cannot accept traces
- **THEN** requests and worker processing continue with their existing outcomes and trace data is dropped or buffered within configured bounds

#### Scenario: Tracing is disabled
- **WHEN** the same protocol operation runs with tracing disabled and enabled
- **THEN** its public response, persisted outcome, and randomness behavior remain equivalent
