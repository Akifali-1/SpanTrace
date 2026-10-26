from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import hashlib
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from .config import get_settings
from .db import Base, engine, get_db
from .graph import build_execution_graph
from .incident import evaluate_incidents
from .integrations import diagnostics_for_project
from .models import ApiKey, InstrumentationConfig, Project, RegressionCase, RegressionRun, RepositoryAnalysis, RepositoryFinding, RepositoryRelationship, Run, TraceEvent
from .repository import (
    RepositoryImportError,
    fetch_public_github_archive,
    load_analysis,
    process_archive,
    read_source_evidence,
    read_upload,
    save_configuration,
    serialize_analysis,
    serialize_config,
)
from .regression import run_booking_regression
from .schemas import EventBatch, InstrumentationConfigSelection, KeyCreate, ProjectCreate, RegressionCaseCreate, RegressionRunRequest, RepositoryUrlImport, event_dict
from .security import issue_key, project_for_key, revoke_key
from .serialization import iso, serialize_event, serialize_run

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="SpanTrace API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_size_guard(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size = int(content_length)
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid content length."})
        if request.url.path == "/v1/ingest/events" and size > settings.max_event_bytes * 2:
            return JSONResponse(status_code=413, content={"detail": "Request payload is too large."})
        if request.url.path.startswith("/v1/repositories/import") and size > settings.repository_max_archive_bytes + 1_048_576:
            return JSONResponse(status_code=413, content={"detail": "Repository archive request is too large."})
    return await call_next(request)


Db = Annotated[Session, Depends(get_db)]


def authenticated_project(db: Session, api_key: str | None) -> Project:
    project = project_for_key(db, api_key)
    if not project:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key.")
    return project


def project_dependency(db: Db, x_api_key: Annotated[str | None, Header()] = None) -> Project:
    return authenticated_project(db, x_api_key)


ProjectDep = Annotated[Project, Depends(project_dependency)]


def run_name_from_event(event: Any) -> str:
    metadata = event.metadata or {}
    return str(metadata.get("run_name") or event.trace_id)


def sync_run_from_event(db: Session, project: Project, event: Any) -> Run:
    run = db.scalar(select(Run).where(Run.project_id == project.id, Run.trace_id == event.trace_id))
    if run is None:
        run = Run(project_id=project.id, trace_id=event.trace_id, name=run_name_from_event(event), started_at=event.occurred_at)
        db.add(run)
        db.flush()
    elif run.name == event.trace_id and run_name_from_event(event) != event.trace_id:
        run.name = run_name_from_event(event)
    if event.metadata:
        run.metadata_json = {**(run.metadata_json or {}), **event.metadata}
    if event.occurred_at < run.started_at:
        run.started_at = event.occurred_at
    if event.event_type == "run_completed":
        if run.status != "failed":
            run.status = event.status if event.status != "running" else "succeeded"
        run.ended_at = event.ended_at or event.occurred_at
    elif event.status == "failed":
        run.status = "failed"
    elif run.status not in {"failed", "succeeded"}:
        run.status = "running"
    if run.ended_at:
        run.duration_ms = max(0, int((run.ended_at - run.started_at).total_seconds() * 1000))
    return run


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "spantrace-api"}


@app.get("/readiness")
def readiness(db: Db) -> dict[str, str]:
    db.execute(select(func.count(Project.id)))
    return {"status": "ready", "database": "ok"}


@app.post("/v1/projects", status_code=201)
def create_project(payload: ProjectCreate, db: Db) -> dict[str, Any]:
    project = Project(name=payload.name.strip())
    db.add(project)
    db.flush()
    key, raw_key = issue_key(db, project)
    db.commit()
    return {
        "project": {"id": project.id, "name": project.name, "created_at": iso(project.created_at)},
        "api_key": raw_key,
        "key_id": key.id,
        "warning": "Store this API key now. It will not be shown again.",
    }


@app.get("/v1/project")
def get_project(project: ProjectDep, db: Db) -> dict[str, Any]:
    keys = db.scalars(select(ApiKey).where(ApiKey.project_id == project.id).order_by(ApiKey.created_at.desc())).all()
    return {
        "id": project.id,
        "name": project.name,
        "created_at": iso(project.created_at),
        "keys": [{"id": key.id, "name": key.name, "prefix": key.prefix, "created_at": iso(key.created_at), "revoked_at": iso(key.revoked_at)} for key in keys],
    }


@app.post("/v1/project/keys", status_code=201)
def create_key(payload: KeyCreate, project: ProjectDep, db: Db) -> dict[str, Any]:
    key, raw_key = issue_key(db, project, payload.name)
    db.commit()
    return {"key_id": key.id, "api_key": raw_key, "warning": "Store this API key now. It will not be shown again."}


@app.delete("/v1/project/keys/{key_id}")
def delete_key(key_id: str, project: ProjectDep, db: Db) -> dict[str, str]:
    key = db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.project_id == project.id))
    if not key:
        raise HTTPException(status_code=404, detail="Key not found.")
    revoke_key(key)
    db.commit()
    return {"status": "revoked"}


@app.post("/v1/ingest/events")
def ingest_events(payload: EventBatch, project: ProjectDep, db: Db) -> dict[str, Any]:
    accepted = 0
    duplicate = 0
    run_ids: set[str] = set()
    for event in payload.events:
        # Pydantic has already rejected malformed fields. The extra-field policy
        # lets forward-compatible adapters send fields this server does not yet use.
        if len(event.model_dump_json()) > settings.max_event_bytes:
            raise HTTPException(status_code=413, detail=f"Event {event.event_id} is too large.")
        existing = db.scalar(select(TraceEvent).where(TraceEvent.project_id == project.id, TraceEvent.event_id == event.event_id))
        if existing:
            duplicate += 1
            continue
        data = event_dict(event)
        run = sync_run_from_event(db, project, event)
        data.pop("trace_id", None)
        data["project_id"] = project.id
        data["run_id"] = run.id
        db.add(TraceEvent(**data))
        run.event_count += 1
        run_ids.add(run.trace_id)
        accepted += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # A concurrent retry can race the duplicate pre-check. The client can
        # safely retry; no partial response is advertised as accepted.
        raise HTTPException(status_code=409, detail="Duplicate event submission raced with another request.")
    return {"accepted": accepted, "duplicates": duplicate, "trace_ids": sorted(run_ids)}


@app.get("/v1/runs")
def list_runs(
    project: ProjectDep,
    db: Db,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    agent: str | None = None,
    since: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    query = select(Run).where(Run.project_id == project.id)
    if status_filter:
        query = query.where(Run.status == status_filter)
    if since:
        query = query.where(Run.started_at >= since)
    if agent:
        query = query.join(TraceEvent).where(TraceEvent.agent_name == agent).distinct()
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    runs = db.scalars(query.options(selectinload(Run.events)).order_by(Run.started_at.desc()).offset(offset).limit(limit)).all()
    return {"items": [serialize_run(run, evaluate_incidents(run.events)) for run in runs], "total": total, "limit": limit, "offset": offset}


@app.get("/v1/runs/{trace_id}")
def get_run(trace_id: str, project: ProjectDep, db: Db) -> dict[str, Any]:
    run = db.scalar(select(Run).options(joinedload(Run.events)).where(Run.project_id == project.id, Run.trace_id == trace_id))
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    incidents = evaluate_incidents(run.events)
    result = serialize_run(run, incidents)
    lifecycle_order = {"run_started": 0, "run_completed": 2}
    ordered_events = sorted(run.events, key=lambda item: (item.occurred_at, lifecycle_order.get(item.event_type, 1)))
    result["events"] = [serialize_event(event) for event in ordered_events]
    result["graph"] = build_execution_graph(ordered_events)
    return result


@app.get("/v1/integrations")
def list_integrations(project: ProjectDep, db: Db) -> dict[str, Any]:
    return {"items": diagnostics_for_project(db, project)}


def _repository_error(exc: RepositoryImportError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@app.post("/v1/repositories/import/url", status_code=201)
def import_repository_url(payload: RepositoryUrlImport, project: ProjectDep, db: Db) -> dict[str, Any]:
    try:
        archive, metadata = fetch_public_github_archive(payload.url, payload.ref, settings)
        analysis, reused = process_archive(
            db,
            project,
            archive,
            source_kind="github",
            name=metadata["name"],
            source_url=metadata["source_url"],
            branch=metadata["branch"],
            commit_sha=metadata["commit_sha"],
            source_revision=metadata["source_revision"],
            settings=settings,
        )
    except RepositoryImportError as exc:
        raise _repository_error(exc) from exc
    return {"analysis": serialize_analysis(load_analysis(db, project.id, analysis.id) or analysis, include_findings=True), "reused": reused}


@app.post("/v1/repositories/import/zip", status_code=201)
async def import_repository_zip(project: ProjectDep, db: Db, file: UploadFile = File(...)) -> dict[str, Any]:
    try:
        archive, name = await read_upload(file, settings)
        analysis, reused = process_archive(
            db,
            project,
            archive,
            source_kind="zip",
            name=name,
            source_url=None,
            branch=None,
            commit_sha=None,
            source_revision=f"archive:{hashlib.sha256(archive).hexdigest()[:16]}",
            settings=settings,
        )
    except RepositoryImportError as exc:
        raise _repository_error(exc) from exc
    return {"analysis": serialize_analysis(load_analysis(db, project.id, analysis.id) or analysis, include_findings=True), "reused": reused}


@app.get("/v1/repositories")
def list_repository_analyses(project: ProjectDep, db: Db, limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    analyses = db.scalars(select(RepositoryAnalysis).where(RepositoryAnalysis.project_id == project.id).order_by(RepositoryAnalysis.created_at.desc()).limit(limit)).all()
    return {"items": [serialize_analysis(analysis) for analysis in analyses]}


@app.get("/v1/repositories/{analysis_id}")
def get_repository_analysis(analysis_id: str, project: ProjectDep, db: Db) -> dict[str, Any]:
    analysis = load_analysis(db, project.id, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Repository analysis not found.")
    return serialize_analysis(analysis, include_findings=True)


@app.post("/v1/repositories/{analysis_id}/reanalyze")
def reanalyze_repository(analysis_id: str, project: ProjectDep, db: Db) -> dict[str, Any]:
    analysis = load_analysis(db, project.id, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Repository analysis not found.")
    if not analysis.source_path:
        raise HTTPException(status_code=409, detail="Source is no longer available for this analysis.")
    from .discovery import analyze_repository
    from .repository import _persist_result

    analysis.status = "analyzing"
    analysis.error_message = None
    db.commit()
    db.execute(delete(RepositoryRelationship).where(RepositoryRelationship.analysis_id == analysis.id))
    db.execute(delete(RepositoryFinding).where(RepositoryFinding.analysis_id == analysis.id))
    result = analyze_repository(analysis.source_path, settings)
    _persist_result(db, analysis, result)
    analysis.analysis_version += 1
    analysis.summary_json = result.summary
    analysis.limitations_json = result.limitations
    analysis.status = "partially_analyzed" if result.partially_analyzed else "analysis_complete"
    analysis.analyzed_at = datetime.utcnow()
    analysis.updated_at = datetime.utcnow()
    for configuration in analysis.configurations:
        configuration.stale = True
        configuration.updated_at = datetime.utcnow()
    db.commit()
    return {"analysis": serialize_analysis(load_analysis(db, project.id, analysis.id) or analysis, include_findings=True), "reused": False}


@app.get("/v1/repositories/{analysis_id}/source")
def get_repository_source_evidence(
    analysis_id: str,
    project: ProjectDep,
    db: Db,
    path: str = Query(min_length=1, max_length=500),
    start_line: int = Query(default=1, ge=1, le=1_000_000),
    end_line: int = Query(default=1, ge=1, le=1_000_000),
) -> dict[str, Any]:
    analysis = db.scalar(select(RepositoryAnalysis).where(RepositoryAnalysis.id == analysis_id, RepositoryAnalysis.project_id == project.id))
    if not analysis:
        raise HTTPException(status_code=404, detail="Repository analysis not found.")
    if end_line < start_line:
        raise HTTPException(status_code=422, detail="end_line must be greater than or equal to start_line.")
    return read_source_evidence(analysis, path, start_line, min(end_line, start_line + 79))


@app.get("/v1/repositories/{analysis_id}/config")
def get_repository_config(analysis_id: str, project: ProjectDep, db: Db) -> dict[str, Any]:
    analysis = load_analysis(db, project.id, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Repository analysis not found.")
    config = max(analysis.configurations, key=lambda item: item.version, default=None)
    return {"configuration": serialize_config(config)}


@app.post("/v1/repositories/{analysis_id}/config", status_code=201)
def create_repository_config(analysis_id: str, payload: InstrumentationConfigSelection, project: ProjectDep, db: Db) -> dict[str, Any]:
    analysis = load_analysis(db, project.id, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Repository analysis not found.")
    config = save_configuration(db, project, analysis, payload)
    return {"configuration": serialize_config(config)}


@app.get("/v1/repositories/{analysis_id}/config/export")
def export_repository_config(analysis_id: str, project: ProjectDep, db: Db) -> JSONResponse:
    analysis = load_analysis(db, project.id, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Repository analysis not found.")
    config = max(analysis.configurations, key=lambda item: item.version, default=None)
    if not config:
        raise HTTPException(status_code=404, detail="No instrumentation configuration has been saved.")
    return JSONResponse(content=config.config_json, headers={"Content-Disposition": f'attachment; filename="spantrace-instrumentation-v{config.version}.json"'})


@app.get("/v1/runs/{trace_id}/export")
def export_run(trace_id: str, project: ProjectDep, db: Db) -> dict[str, Any]:
    return get_run(trace_id, project, db)


@app.post("/v1/runs/{trace_id}/regression-case", status_code=201)
def create_regression_case(trace_id: str, payload: RegressionCaseCreate, project: ProjectDep, db: Db) -> dict[str, Any]:
    run = db.scalar(select(Run).where(Run.project_id == project.id, Run.trace_id == trace_id))
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    incidents = evaluate_incidents(run.events)
    if not incidents:
        raise HTTPException(status_code=422, detail="A regression case requires a recorded incident.")
    case = RegressionCase(
        project_id=project.id,
        source_trace_id=trace_id,
        name=payload.name,
        scenario={"type": "travel_booking", "destination": "Goa", "nights": 2, "max_price_inr": 5000, "approval_required": True},
        expected_assertions=[{"rule": "reservation_requires_approval", "reservation_created_while_pending": False}],
    )
    db.add(case)
    db.commit()
    return regression_case_json(case)


def regression_case_json(case: RegressionCase) -> dict[str, Any]:
    return {"id": case.id, "name": case.name, "source_trace_id": case.source_trace_id, "scenario": case.scenario, "expected_assertions": case.expected_assertions, "created_at": iso(case.created_at)}


@app.get("/v1/regression-cases")
def list_regression_cases(project: ProjectDep, db: Db) -> dict[str, Any]:
    cases = db.scalars(select(RegressionCase).where(RegressionCase.project_id == project.id).order_by(RegressionCase.created_at.desc())).all()
    results = db.scalars(select(RegressionRun).join(RegressionCase).where(RegressionCase.project_id == project.id).order_by(RegressionRun.created_at.desc())).all()
    latest: dict[str, RegressionRun] = {}
    for result in results:
        latest.setdefault(result.case_id, result)
    return {
        "items": [
            {**regression_case_json(case), "latest_result": {"id": latest[case.id].id, "passed": latest[case.id].passed, "actual": latest[case.id].actual, "created_at": iso(latest[case.id].created_at)} if case.id in latest else None}
            for case in cases
        ]
    }


@app.post("/v1/regression-cases/{case_id}/run")
def run_regression(case_id: str, payload: RegressionRunRequest, project: ProjectDep, db: Db) -> dict[str, Any]:
    case = db.scalar(select(RegressionCase).where(RegressionCase.id == case_id, RegressionCase.project_id == project.id))
    if not case:
        raise HTTPException(status_code=404, detail="Regression case not found.")
    actual = run_booking_regression(payload.fixed)
    result = RegressionRun(case_id=case.id, passed=actual["passed"], actual=actual)
    db.add(result)
    db.commit()
    return {"id": result.id, "case_id": case.id, "passed": result.passed, "actual": actual, "created_at": iso(result.created_at)}
