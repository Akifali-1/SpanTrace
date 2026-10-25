# AgentScope Task 1 architecture

## Components

- `packages/python-sdk/agentscope`: dependency-free manual instrumentation client. It creates trace and span events, propagates current trace/span through `contextvars`, redacts sensitive keys, buffers events, and submits authenticated batches.
- `services/api/app`: FastAPI modular monolith. Pydantic validates incoming event batches, SQLAlchemy persists project-scoped data, and API-key authentication resolves a project from a stored hash.
- `apps/web`: Next.js App Router dashboard. Browser requests go through a server-side route handler that adds `X-API-Key`, keeping the project secret out of frontend JavaScript.
- `examples/travel_booking`: deterministic multi-agent scenario with planner, hotel search, budget validation, approval policy, booking, final response, and a mock booking service.

## Trace contract

Every event has a schema version, stable event ID, trace ID, optional span and parent span IDs, event type, kind, status, timestamps, optional duration, selected inputs and outputs, tool fields, handoff target, error fields, and extensible metadata. The API accepts unknown fields for forward-compatible adapters while persisting the supported common subset.

The event types used by the demo are `run_started`, `agent_span`, `tool_call`, `handoff`, `exception`, and `run_completed`. The model is framework-independent: adapters can normalize framework callbacks into the same event shape without making the backend understand each framework.

## Ingestion and persistence

Clients send `POST /v1/ingest/events` with an API key in `X-API-Key`. Events are scoped by the project resolved from the hashed key. The `(project_id, event_id)` unique constraint makes retries idempotent. Runs are keyed by `(project_id, trace_id)` and remain `running` until a completion event arrives; out-of-order timestamps are normalized by the earliest observed start and completion event.

SQLite is the zero-dependency local default. PostgreSQL is supported by the same SQLAlchemy model and the committed Alembic migration. The API enforces batch counts, event payload sizes, field limits, and a configurable CORS allowlist.

## Incident evaluation

The first detector is intentionally deterministic and evidence-based. It records the latest observed approval state from approval/policy events. When a `create_reservation` tool result contains a reservation while the recorded state is `pending` or `denied`, it emits a high-severity incident tied to the violating event and cites both evidence events. When approval state is absent, it emits an `unknown` incident rather than claiming a violation.

This is not an LLM-based general root-cause engine. It does not infer policy from arbitrary prose or claim coverage beyond the configured rule.

## Regression foundation

Creating a case from an incident stores the source trace ID, travel scenario, and expected invariant. The runner has one explicit built-in scenario and two modes: defective (reservation created while pending) and corrected (booking waits). No user code is uploaded, deserialized, or executed by the API.

## Security boundaries and limitations

- Raw project keys are returned once on project/key creation; only hashes and prefixes are persisted.
- Protected endpoints require a valid non-revoked project key, and all run/event/case queries include project scope.
- Payload capture can be disabled, and the SDK redacts common secret keys before submission. Redaction is configurable but callers remain responsible for avoiding sensitive data in custom values.
- SDK submission fails open by default and retains buffered events for a later flush; `strict=True` raises when the backend is unavailable.
- There is no SSE stream in Task 1. The dashboard uses request/refresh behavior because reliable ingestion and persistence take priority.
- The local API uses `create_all` for first-run convenience; production deployments should apply Alembic migrations and configure PostgreSQL.
- Retention is represented in configuration but automatic cleanup is deferred.
- The dashboard currently represents one project through the server-side API-key configuration; multi-project login and organization management are outside this slice.
