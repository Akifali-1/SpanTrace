# AgentScope

AgentScope is a local-first developer platform for understanding multi-agent executions. Task 1 delivers one complete vertical slice:

**capture → persist → inspect → detect a policy incident → create a regression case → verify the corrected behavior**

The repository is intentionally a modular monolith. The API and dashboard are separate applications, while the Python SDK is a standalone dependency-free package that can be used by another Python application.

## Prerequisites

- Python 3.11+
- Node.js 22+
- npm 10+
- Docker and Docker Compose are optional. Docker is not installed in the current development container, so local SQLite mode is the supported verification path here.

## AgentScope local ports

AgentScope uses ports that do not overlap with the other projects in your map:

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

The API defaults to SQLite at `./agentscope.db`. For PostgreSQL, set `AGENTSCOPE_DATABASE_URL` to a SQLAlchemy PostgreSQL URL and run the migration command below. The compose file provides a Postgres 16 service and an API image for environments with Docker.

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
AGENTSCOPE_API_URL=http://localhost:8070
AGENTSCOPE_API_KEY=ask_...
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

Export the `AGENTSCOPE_PROJECT_ID` and `AGENTSCOPE_API_KEY` values printed by the command. The raw API key is displayed only in this bootstrap response and is stored only as a SHA-256 hash by the API.

## Run the travel-booking demo

The example uses only a deterministic in-process mock booking API. It never calls a real hotel provider and never makes a reservation.

```bash
export AGENTSCOPE_API_URL=http://localhost:8070
export AGENTSCOPE_PROJECT_ID=<project-id>
export AGENTSCOPE_API_KEY=<project-key>

PYTHONPATH=packages/python-sdk python3 examples/travel_booking/main.py --mode normal
PYTHONPATH=packages/python-sdk python3 examples/travel_booking/main.py --mode failure
```

The `failure` run records `approval_state=pending` and then deliberately calls the mock `create_reservation` tool. It is defective demo code only; it does not weaken AgentScope authorization or execute code supplied through the API. Open Runs in the dashboard and inspect the trace detail page to see the recorded evidence.

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
python3 scripts/run_regression.py create --api-key "$AGENTSCOPE_API_KEY" --trace-id <failed-trace-id>
python3 scripts/run_regression.py run --api-key "$AGENTSCOPE_API_KEY" --case-id <case-id> --fixed
```

The regression case stores its scenario, expected assertion, and source trace ID. The server-side runner is deliberately restricted to this known mock scenario and does not execute arbitrary uploaded source code.

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

The current test suite covers nested SDK spans, context relationships, redaction, fail-open/fail-closed network behavior, ingestion idempotency, invalid payloads, project isolation, filters, incident evidence, regression pass/fail behavior, and demo execution.

## Database migrations

The API creates tables automatically for a convenient SQLite first run. The committed Alembic migration is the source of truth for managed environments:

```bash
AGENTSCOPE_DATABASE_URL=postgresql+psycopg://... alembic upgrade head
```

The Dockerfile installs `psycopg` when building the API image. Install `psycopg[binary]` locally if you run the PostgreSQL migration command outside Docker.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the trace event contract, ingestion flow, storage model, SDK boundaries, incident evaluation, and known limitations.
