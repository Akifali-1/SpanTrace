# SpanTrace Task 2 architecture

## Components

- `packages/python-sdk/agentscope`: compatibility SDK module. `packages/python-sdk/spantrace` is the canonical import path. The client creates manual events, propagates current trace/span through `contextvars`, supports async context managers, redacts sensitive keys, bounds payloads, deduplicates stable event IDs, buffers events, and submits authenticated batches.
- `packages/python-sdk/agentscope/integrations`: opt-in adapter layer. `OpenTelemetryAdapter` exports completed public OpenTelemetry spans; `CallbackAdapter` normalizes framework callback/listener events without monkey-patching arbitrary functions.
- `services/api/app`: FastAPI modular monolith. Pydantic validates incoming event batches, SQLAlchemy persists project-scoped data, and API-key authentication resolves a project from a stored hash.
- `apps/web`: Next.js App Router dashboard. Browser requests go through a server-side route handler that adds `X-API-Key`, keeping the project secret out of frontend JavaScript. Run detail includes a conservative execution graph and a chronological fallback; settings includes integration diagnostics.
- `examples/travel_booking`: deterministic multi-agent scenario with planner, hotel search, budget validation, approval policy, booking, final response, and a mock booking service.

## Trace contract

Every event has a schema version, stable event ID, trace ID, optional span and parent span IDs, event type, kind, status, timestamps, optional duration, selected inputs and outputs, tool/model fields, handoff target, integration/framework identifiers, relationship confidence, error fields, and extensible metadata. The API accepts unknown fields for forward-compatible adapters while persisting the supported common subset.

The event types used by the demo include `run_started`, `agent_span`, `model_call`, `tool_call`, `handoff`, `exception`, and `run_completed`. The model is framework-independent: adapters normalize framework callbacks or OpenTelemetry spans into the same event shape without making the backend understand each framework.

## Ingestion and persistence

Clients send `POST /v1/ingest/events` with an API key in `X-API-Key`. Events are scoped by the project resolved from the hashed key. The `(project_id, event_id)` unique constraint makes retries idempotent. Runs are keyed by `(project_id, trace_id)` and remain `running` until a completion event arrives; out-of-order timestamps are normalized by the earliest observed start and completion event.

SQLite is the zero-dependency local default. PostgreSQL is supported by the same SQLAlchemy model and the committed Alembic migration. The API enforces batch counts, event payload sizes, field limits, and a configurable CORS allowlist.

## Incident evaluation

The first detector is intentionally deterministic and evidence-based. It records the latest observed approval state from approval/policy events. When a `create_reservation` tool result contains a reservation while the recorded state is `pending` or `denied`, it emits a high-severity incident tied to the violating event and cites both evidence events. When approval state is absent, it emits an `unknown` incident rather than claiming a violation.

This is not an LLM-based general root-cause engine. It does not infer policy from arbitrary prose or claim coverage beyond the configured rule.

## Automatic instrumentation and reconstruction

OpenTelemetry is the primary automatic integration because it is a public, framework-independent instrumentation boundary. The exporter emits one normalized event per completed span and preserves OpenTelemetry trace/span/parent IDs. Span attributes such as `spantrace.kind`, `spantrace.event_type`, `spantrace.tool_name`, `spantrace.model_name`, and `spantrace.*` payload fields add semantic detail when an application or framework exposes it. Span events named `exception` and `spantrace.handoff` are retained as separate events.

The callback adapter is the deterministic fallback for frameworks with callback APIs. It exposes explicit lifecycle methods rather than patching arbitrary functions. Adapters are best-effort by default because telemetry failures must not crash the application; strict SDK mode remains available for development and verification.

The API builds a graph only from observed parent span IDs and explicit handoff metadata. A handoff without a target span is shown as unresolved, and incomplete traces receive `partially_observed` status. The dashboard always retains the chronological event timeline so missing graph relationships do not disappear.

## Regression foundation

Creating a case from an incident stores the source trace ID, travel scenario, and expected invariant. The runner has one explicit built-in scenario and two modes: defective (reservation created while pending) and corrected (booking waits). No user code is uploaded, deserialized, or executed by the API.

## Security boundaries and limitations

- Raw project keys are returned once on project/key creation; only hashes and prefixes are persisted.
- Protected endpoints require a valid non-revoked project key, and all run/event/case queries include project scope.
- Payload capture can be disabled, and the SDK redacts common secret keys before submission. Redaction is configurable but callers remain responsible for avoiding sensitive data in custom values.
- SDK submission fails open by default and retains buffered events for a later flush; `strict=True` raises when the backend is unavailable.
- There is no SSE stream in Task 2. The dashboard uses request/refresh behavior because reliable ingestion and persistence take priority.
- Framework-specific internal events are unavailable unless the framework exposes them through OpenTelemetry or a supported callback. SpanTrace does not claim universal agent discovery.
- The OpenTelemetry adapter currently exports completed spans; application-specific attribute conventions are required for rich prompt/tool payloads and exact handoff targets.
- The local API uses `create_all` for first-run convenience; production deployments should apply Alembic migrations and configure PostgreSQL.
- Retention is represented in configuration but automatic cleanup is deferred.
- The dashboard currently represents one project through the server-side API-key configuration; multi-project login and organization management are outside this slice.
