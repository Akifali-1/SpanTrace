# SpanTrace

SpanTrace is a local-first developer platform for understanding multi-agent executions. The original Task 1 `agentscope` import and environment variables remain compatible while the product and new SDK path use SpanTrace.

**capture → persist → inspect → detect a policy incident → create a regression case → verify the corrected behavior**

The repository is intentionally a modular monolith. The API and dashboard are separate applications, while the Python SDK is a standalone dependency-free package that can be used by another Python application.

## Prerequisites

- Python 3.11+
- Node.js 22+
- npm 10+
- Docker and Docker Compose are optional. Docker is not installed in the current development container, so local SQLite mode is the supported verification path here.

## SpanTrace local ports

SpanTrace uses ports that do not overlap with the other projects in your map:

| Surface | Port | URL |
| --- | ---: | --- |
| Dashboard | `3070` | http://localhost:3070 |
| API | `8070` | http://localhost:8070 |

The Docker Compose API mapping is `8070:8000`; the container still listens on its internal port `8000`.

## Local setup

```bash
python3 -m pip install -r requirements.txt
cd apps/web && npm install
cd ../..
```

The API defaults to SQLite at `./agentscope.db`. For PostgreSQL, set `SPANTRACE_DATABASE_URL` to a SQLAlchemy PostgreSQL URL and run the migration command below. Legacy `AGENTSCOPE_` server variables remain accepted. The compose file provides a Postgres 16 service and an API image for environments with Docker.

## Start the API

```bash
PYTHONPATH=services/api:packages/python-sdk python3 -m uvicorn app.main:app --reload --port 8070
```

Health checks:

```bash
curl http://localhost:8070/health
curl http://localhost:8070/readiness
```

## Start the dashboard

Create `apps/web/.env.local` with the API URL and a project key after bootstrapping a project. This file is ignored by Git.

```bash
SPANTRACE_API_URL=http://localhost:8070
SPANTRACE_API_KEY=ask_...
```

Then run:

```bash
cd apps/web
npm run dev
```

Open http://localhost:3070. The Next.js server proxy keeps the project key server-side; it is never placed in browser code.

## Create a demo project

With the API running:

```bash
python3 scripts/bootstrap_demo.py
```

Export the `SPANTRACE_PROJECT_ID` and `SPANTRACE_API_KEY` values printed by the command. The raw API key is displayed only in this bootstrap response and is stored only as a SHA-256 hash by the API.

## Run the travel-booking demo

The example uses only a deterministic in-process mock booking API. It never calls a real hotel provider and never makes a reservation.

```bash
export SPANTRACE_API_URL=http://localhost:8070
export SPANTRACE_PROJECT_ID=<project-id>
export SPANTRACE_API_KEY=<project-key>

PYTHONPATH=packages/python-sdk python3 examples/travel_booking/main.py --mode normal --integration opentelemetry
PYTHONPATH=packages/python-sdk python3 examples/travel_booking/main.py --mode failure --integration opentelemetry
```

The `failure` run records `approval_state=pending` and then deliberately calls the mock `create_reservation` tool. It is defective demo code only; it does not weaken SpanTrace authorization or execute code supplied through the API. Open Runs in the dashboard and inspect the trace detail page to see the recorded evidence.

The default OpenTelemetry path uses public OpenTelemetry SDK APIs and does not wrap the agents, model, or tool calls with SpanTrace-specific context managers. Use `--integration manual` to run the Task 1 compatibility path.

The other modes are:

- `normal`: waits for approval and does not create a reservation.
- `approved`: records approval and creates the mock reservation.
- `fixed`: demonstrates the corrected implementation behavior in the deterministic regression runner.

## Incident and regression workflow

From the failed trace detail page:

1. Review the incident evidence and the violating tool event.
2. Select **Create regression case**.
3. Select **Run corrected case**.
4. The result should say that the corrected booking waits for approval and passes the invariant.

The equivalent CLI flow is:

```bash
python3 scripts/run_regression.py create --api-key "$SPANTRACE_API_KEY" --trace-id <failed-trace-id>
python3 scripts/run_regression.py run --api-key "$SPANTRACE_API_KEY" --case-id <case-id> --fixed
```

The regression case stores its scenario, expected assertion, and source trace ID. The server-side runner is deliberately restricted to this known mock scenario and does not execute arbitrary uploaded source code.

## Automatic instrumentation

The canonical SDK import is:

```python
from spantrace import SpanTrace

scope = SpanTrace.from_env()
provider, adapter = scope.instrument_opentelemetry(service_name="my-workflow", framework="my-framework")
tracer = provider.get_tracer("my-app")
```

SpanTrace also provides `CallbackAdapter` for frameworks that expose supported lifecycle callbacks but do not emit OpenTelemetry spans. The adapter normalizes workflow, node/agent, model, tool, handoff, retry, exception, and completion events while preserving framework IDs. It is opt-in and does not monkey-patch arbitrary functions.

Payload capture is configurable with `SPANTRACE_CAPTURE_PAYLOADS` (the `AGENTSCOPE_` prefix remains supported), and exported payloads are redacted for common credentials and bounded by a size limit. Automatic instrumentation reports missing parent IDs and unresolved handoffs as partial observation rather than guessing a relationship.

### Support matrix

| Integration | Status | Tested path |
| --- | --- | --- |
| OpenTelemetry SDK | Tested | `opentelemetry-api/sdk==1.29.0`; spans, model/tool attributes, exceptions, handoff events |
| SpanTrace callback contract | Tested | deterministic callback adapter; lifecycle, retries, errors, handoffs |
| LangGraph | Experimental | Use its callback/OpenTelemetry bridge when configured; framework-specific coverage depends on exposed events |
| OpenAI Agents SDK | Planned | No adapter is claimed until a compatible public callback contract is verified |

### Missing events and troubleshooting

The Settings page reports `no events received`, `events received`, or `partially observed` using persisted telemetry evidence. A partial trace usually means the source did not expose a root/completion event, a parent ID was not available, or a handoff target was not identified. Check the framework's callback configuration, keep the provider alive until the workflow finishes, and call `provider.shutdown()` or `scope.shutdown()` at process exit.

## Tests and checks

Run the backend, SDK, and demo tests:

```bash
python3 -m pytest -q
```

Run frontend checks:

```bash
cd apps/web
npm run typecheck
npm run build
```

The current test suite covers nested SDK spans, async context relationships, callback and OpenTelemetry lifecycle capture, redaction, fail-open/fail-closed network behavior, ingestion idempotency, invalid payloads, project isolation, filters, graph reconstruction, integration diagnostics, incident evidence, regression pass/fail behavior, and demo execution.

## Database migrations

The API creates tables automatically for a convenient SQLite first run. The committed Alembic migration is the source of truth for managed environments:

```bash
AGENTSCOPE_DATABASE_URL=postgresql+psycopg://... alembic upgrade head
```

The Dockerfile installs `psycopg` when building the API image. Install `psycopg[binary]` locally if you run the PostgreSQL migration command outside Docker.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the trace event contract, ingestion flow, storage model, SDK boundaries, incident evaluation, and known limitations.
