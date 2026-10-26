# SpanTrace Task 3 architecture

## Components

- `packages/python-sdk/agentscope`: compatibility SDK module. `packages/python-sdk/spantrace` is the canonical import path. The client creates manual events, propagates current trace/span through `contextvars`, supports async context managers, redacts sensitive keys, bounds payloads, deduplicates stable event IDs, buffers events, and submits authenticated batches.
- `packages/python-sdk/agentscope/integrations`: opt-in adapter layer. `OpenTelemetryAdapter` exports completed public OpenTelemetry spans; `CallbackAdapter` normalizes framework callback/listener events without monkey-patching arbitrary functions.
- `services/api/app`: FastAPI modular monolith. Pydantic validates incoming event batches, SQLAlchemy persists project-scoped data, and API-key authentication resolves a project from a stored hash.
- `apps/web`: Next.js App Router dashboard. Browser requests go through a server-side route handler that adds `X-API-Key`, keeping the project secret out of frontend JavaScript. Run detail includes a conservative execution graph and a chronological fallback; settings includes integration diagnostics.
- `services/api/app/repository.py`: project-scoped repository ingestion and configuration service. It accepts public GitHub archives and ZIP uploads, validates archive boundaries, stores source under an isolated project/analysis directory, persists analysis versions, and validates exportable instrumentation configuration.
- `services/api/app/discovery.py`: deterministic read-only inventory and Python AST discovery engine. It detects manifests, languages, framework markers, candidate agents/tools/graphs/model calls/entry points, source-supported relationships, environment-variable names, and analysis limitations without importing or executing repository code.
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

## Repository import and discovery

`POST /v1/repositories/import/url` accepts a public HTTPS GitHub repository URL and optional ref. The API calls GitHub's public metadata and codeload endpoints with redirects disabled, records the branch/ref, commit SHA when resolvable, and a SHA-256 archive fingerprint, then analyzes the extracted source. `POST /v1/repositories/import/zip` accepts a bounded multipart ZIP upload. Both flows return actual persisted states (`importing`, `source_available`, `analyzing`, `analysis_complete`, `partially_analyzed`, or `failed`); the current synchronous path completes the state transition before responding.

`repository_analyses` stores source identity, revision, storage path, summary, limitations, and timestamps. `repository_findings` stores source-backed components with stable IDs and evidence locations. `repository_relationships` stores only resolved or explicitly unresolved calls, registrations, delegations, invocations, routes, and external-service uses. `instrumentation_configs` stores validated, versioned configurations tied to one analysis revision. Reimporting the same archive fingerprint reuses a completed analysis instead of duplicating findings; a changed source fingerprint creates a new analysis and marks older configurations stale.

The analyzer walks bounded text files while excluding generated and vendored directories. Python files are parsed with `ast.parse`; syntax errors produce a partial analysis rather than guessed symbols. It detects imports, decorators, agent-like bases, graph construction, tool declarations/registrations, model APIs, HTTP client boundaries, direct local calls, graph edges, delegation calls, conventional entry points, and `__main__` guards. Non-Python languages currently receive inventory-level coverage only. No repository module is imported and no source-derived instruction is treated as an analysis command.

The dashboard's Repository map keeps static architecture separate from runtime traces. Nodes are filterable by type and confidence, edges show their detection evidence, and the selected node exposes a redacted source window. Configuration review supports workflow-entry selection, components, the tested OpenTelemetry adapter, the generic callback adapter, payload capture, and common-secret redaction. Export is JSON schema-shaped and tied to the analyzed source revision.

## Controlled execution MVP

`POST /v1/repositories/{analysis_id}/executions` validates a project-scoped analysis, non-stale instrumentation configuration, selected workflow finding, immutable source snapshot, and bounded JSON input before creating an `execution_runs` record. A small in-process coordinator supervises only Docker CLI lifecycle; it never imports repository code. The worker image in `services/worker` loads the selected Python function inside a short-lived restricted container, applies the selected OpenTelemetry adapter when configured, and emits the existing trace event schema through a short-lived run-scoped token. `GET /v1/executions/{id}` exposes persisted status and sanitized output; cancellation kills the named container; `/v1/executions/{id}/events` verifies the token and exact execution trace ID before forwarding events to normal project-scoped persistence.

The coordinator marks active records as `infrastructure_error` on API restart rather than leaving them running indefinitely. Docker Engine and the prebuilt `spantrace-worker:0.1.0` image are prerequisites. The default worker bridge network is intentionally documented as a limitation because telemetry must reach the API; the worker has no Docker socket, privileged mode, host home mount, or arbitrary host path input. This is controlled execution for one Python entry-point contract, not a universal or perfect sandbox.

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
- Repository source is stored under `.spantrace-data/<project>/<analysis>` by default and is protected by the existing project API-key boundary. Automatic retention cleanup, private GitHub OAuth/app installation, webhook synchronization, and deep non-Python discovery are not implemented.
