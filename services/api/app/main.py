from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from .config import get_settings
from .db import Base, engine, get_db
from .db import SessionLocal
from .execution import ExecutionCoordinator, execution_token, input_fingerprint, serialize_execution, token_hash, redact_value, run_isolated_unittest
from .debugging import (
    build_regression_test,
    collect_failure_evidence,
    copy_isolated_snapshot,
    discover_existing_tests,
    generate_patch,
    rank_root_causes,
    persist_candidates,
    serialize_investigation,
    serialize_candidate,
    serialize_patch,
    serialize_regression_test,
    serialize_reproduction,
    serialize_verification,
    transition_investigation,
    _write_generated_test,
)
from .graph import build_execution_graph
from .incident import evaluate_incidents
from .integrations import diagnostics_for_project
from .models import ApiKey, DebugInvestigation, ExecutionRun, InstrumentationConfig, Project, ProposedPatch, RegressionCase, RegressionRun, RegressionTestArtifact, ReproductionAttempt, RepositoryAnalysis, RepositoryFinding, RepositoryRelationship, RootCauseCandidate, Run, TraceEvent, VerificationRun
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
from .schemas import EventBatch, ExecutionCancel, ExecutionCreate, InstrumentationConfigSelection, InvestigationCreate, KeyCreate, PatchDecision, ProjectCreate, RegressionCaseCreate, RegressionRunRequest, ReproductionRequest, RepositoryUrlImport, VerificationRequest, event_dict
from .security import issue_key, project_for_key, revoke_key
from .serialization import iso, serialize_event, serialize_run

settings = get_settings()
execution_coordinator = ExecutionCoordinator(settings, SessionLocal)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    execution_coordinator.reconcile()
    yield
    execution_coordinator.shutdown()


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


def _ingest_events(payload: EventBatch, project: Project, db: Session, *, expected_trace_id: str | None = None) -> dict[str, Any]:
    accepted = 0
    duplicate = 0
    run_ids: set[str] = set()
    for event in payload.events:
        if expected_trace_id is not None and event.trace_id != expected_trace_id:
            raise HTTPException(status_code=403, detail="Execution telemetry trace does not match the authorized run.")
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


@app.post("/v1/ingest/events")
def ingest_events(payload: EventBatch, project: ProjectDep, db: Db) -> dict[str, Any]:
    return _ingest_events(payload, project, db)


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


def _execution_for_project(db: Session, project_id: str, execution_id: str) -> ExecutionRun | None:
    return db.scalar(
        select(ExecutionRun)
        .options(joinedload(ExecutionRun.analysis), joinedload(ExecutionRun.configuration))
        .where(ExecutionRun.id == execution_id, ExecutionRun.project_id == project_id)
    )


def _investigation_for_project(db: Session, project_id: str, investigation_id: str) -> DebugInvestigation | None:
    return db.scalar(
        select(DebugInvestigation)
        .options(
            selectinload(DebugInvestigation.candidates),
            selectinload(DebugInvestigation.reproductions),
            selectinload(DebugInvestigation.regression_tests),
            selectinload(DebugInvestigation.patches),
            selectinload(DebugInvestigation.verifications),
        )
        .where(DebugInvestigation.id == investigation_id, DebugInvestigation.project_id == project_id)
    )


def _run_for_trace(db: Session, project_id: str, trace_id: str) -> Run | None:
    return db.scalar(select(Run).options(selectinload(Run.events)).where(Run.project_id == project_id, Run.trace_id == trace_id))


def _create_debug_execution(db: Session, project: Project, original: ExecutionRun, *, source_override_path: str | None, idempotency_key: str, input_value: dict[str, Any] | None = None, source_revision: str | None = None) -> ExecutionRun:
    raw_token = execution_token()
    execution = ExecutionRun(
        project_id=project.id,
        analysis_id=original.analysis_id,
        configuration_id=original.configuration_id,
        source_revision=source_revision or original.source_revision,
        archive_fingerprint=original.archive_fingerprint,
        entry_finding_id=original.entry_finding_id,
        entry_file_path=original.entry_file_path,
        entry_symbol=original.entry_symbol,
        trace_id=uuid4().hex,
        idempotency_key=idempotency_key,
        status="queued",
        input_json=redact_value(input_value if input_value is not None else (original.input_json or {})),
        input_fingerprint=input_fingerprint(input_value if input_value is not None else (original.input_json or {})),
        execution_token_hash=token_hash(raw_token),
        execution_token_prefix=raw_token[:16],
        result_json={},
        logs_text="",
        timeout_seconds=original.timeout_seconds,
        memory_mb=original.memory_mb,
        cpu_limit=original.cpu_limit,
        pids_limit=original.pids_limit,
        source_override_path=source_override_path,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    execution_coordinator.submit(execution.id, raw_token, input_value if input_value is not None else (original.input_json or {}))
    return execution


def _sync_reproduction(db: Session, attempt: ReproductionAttempt) -> None:
    if attempt.status not in {"pending", "running"} or not attempt.reproduction_execution_id:
        return
    execution = db.get(ExecutionRun, attempt.reproduction_execution_id)
    if execution:
        db.refresh(execution)
    if not execution or execution.status not in {"succeeded", "failed", "timed_out", "cancelled", "infrastructure_error"}:
        return
    original = db.get(ExecutionRun, attempt.original_execution_id) if attempt.original_execution_id else None
    attempt.reproduction_trace_id = execution.trace_id
    attempt.logs_text = execution.logs_text or ""
    attempt.result_json = {"execution_status": execution.status, "failure_category": execution.failure_category, "result": execution.result_json or {}}
    attempt.completed_at = datetime.utcnow()
    if execution.status == "infrastructure_error":
        attempt.status = "blocked"
        attempt.differences_json = [execution.failure_category or "The controlled worker could not start."]
    elif execution.status == "succeeded":
        attempt.status = "not_reproduced"
        attempt.signature_match = False
        attempt.differences_json = ["The reproduction exited successfully while the original execution was unsuccessful."]
    elif execution.status in {"timed_out", "cancelled"}:
        attempt.status = "inconclusive"
        attempt.signature_match = False
        attempt.differences_json = [f"The reproduction ended as {execution.status}; the original failure signature was not comparable."]
    else:
        original_category = original.failure_category if original else None
        match = bool(original_category and execution.failure_category == original_category)
        attempt.signature_match = match
        attempt.status = "reproduced" if match else "inconclusive"
        if not match:
            attempt.differences_json = [f"Original category={original_category or 'unknown'}; reproduction category={execution.failure_category or 'unknown'}."]


def _sync_verification(db: Session, investigation: DebugInvestigation, verification: VerificationRun) -> None:
    if verification.status != "running" or not verification.patched_execution_id:
        return
    execution = db.get(ExecutionRun, verification.patched_execution_id)
    if execution:
        db.refresh(execution)
    if not execution or execution.status not in {"succeeded", "failed", "timed_out", "cancelled", "infrastructure_error"}:
        return
    verification.patched_trace_id = execution.trace_id
    verification.completed_at = datetime.utcnow()
    tests_passed = verification.patched_test_json.get("status") == "passed" and verification.existing_tests_json.get("status") == "passed"
    workflow_passed = execution.status == "succeeded"
    verification.report_json = {
        **(verification.report_json or {}),
        "original_outcome": {"execution_id": verification.original_execution_id, "trace_id": verification.original_trace_id, "outcome": "failed"},
        "patched_outcome": {"execution_id": execution.id, "trace_id": execution.trace_id, "status": execution.status, "failure_category": execution.failure_category, "result": redact_value(execution.result_json or {})},
        "comparison": {"regression_test_passed": verification.patched_test_json.get("status") == "passed", "existing_tests_passed": verification.existing_tests_json.get("status") == "passed", "controlled_rerun_passed": workflow_passed},
    }
    if execution.status == "infrastructure_error":
        verification.status = "blocked"
        verification.error_message = execution.failure_category or "The patched controlled rerun was blocked by infrastructure."
        target = "blocked"
    elif tests_passed and workflow_passed:
        verification.status = "verified"
        target = "verified"
    else:
        verification.status = "failed"
        target = "failed"
    if investigation.status == "verifying":
        transition_investigation(investigation, target)


@app.get("/v1/executions")
def list_executions(project: ProjectDep, db: Db, limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    executions = db.scalars(select(ExecutionRun).where(ExecutionRun.project_id == project.id).order_by(ExecutionRun.created_at.desc()).limit(limit)).all()
    return {"items": [serialize_execution(item, include_logs=False) for item in executions]}


@app.get("/v1/executions/{execution_id}")
def get_execution(execution_id: str, project: ProjectDep, db: Db) -> dict[str, Any]:
    execution = _execution_for_project(db, project.id, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found.")
    result = serialize_execution(execution)
    run = db.scalar(select(Run).where(Run.project_id == project.id, Run.trace_id == execution.trace_id))
    result["trace_available"] = run is not None
    return result


def _create_investigation(db: Session, project: Project, payload: InvestigationCreate, *, execution: ExecutionRun | None, run: Run | None) -> DebugInvestigation:
    if not execution and not run:
        raise HTTPException(status_code=404, detail="The original execution or trace was not found.")
    if execution and execution.status not in {"failed", "timed_out", "cancelled", "infrastructure_error", "succeeded"} and (not run or run.status not in {"failed", "cancelled"}):
        raise HTTPException(status_code=422, detail="An investigation must start from a completed or failed execution.")
    trace_id = execution.trace_id if execution else run.trace_id
    existing = db.scalar(select(DebugInvestigation).where(DebugInvestigation.project_id == project.id, DebugInvestigation.original_trace_id == trace_id, DebugInvestigation.status.not_in({"cancelled"})).order_by(DebugInvestigation.created_at.desc()))
    if existing:
        return existing
    analysis = db.get(RepositoryAnalysis, execution.analysis_id) if execution else None
    evidence = collect_failure_evidence(execution, run, analysis)
    investigation = DebugInvestigation(
        project_id=project.id,
        original_execution_id=execution.id if execution else None,
        original_trace_id=trace_id,
        analysis_id=analysis.id if analysis else None,
        source_revision=execution.source_revision if execution else (analysis.source_revision if analysis else None),
        archive_fingerprint=execution.archive_fingerprint if execution else (analysis.archive_fingerprint if analysis else None),
        name=payload.name.strip(),
        status="analyzing",
        failure_category=evidence["failure_category"],
        failure_summary=evidence["failure_summary"],
        evidence_json=redact_value(evidence),
        missing_evidence_json=evidence["missing_evidence"],
    )
    db.add(investigation)
    db.flush()
    candidates = rank_root_causes(evidence, execution, run, analysis)
    persist_candidates(db, investigation, candidates)
    transition_investigation(investigation, "open")
    db.commit()
    return investigation


@app.post("/v1/executions/{execution_id}/investigations", status_code=201)
def create_execution_investigation(execution_id: str, payload: InvestigationCreate, project: ProjectDep, db: Db) -> dict[str, Any]:
    execution = _execution_for_project(db, project.id, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found.")
    run = _run_for_trace(db, project.id, execution.trace_id)
    investigation = _create_investigation(db, project, payload, execution=execution, run=run)
    return {"investigation": serialize_investigation(_investigation_for_project(db, project.id, investigation.id) or investigation), "reused": investigation.created_at != investigation.updated_at}


@app.post("/v1/runs/{trace_id}/investigations", status_code=201)
def create_trace_investigation(trace_id: str, payload: InvestigationCreate, project: ProjectDep, db: Db) -> dict[str, Any]:
    run = _run_for_trace(db, project.id, trace_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    execution = db.scalar(select(ExecutionRun).where(ExecutionRun.project_id == project.id, ExecutionRun.trace_id == trace_id))
    investigation = _create_investigation(db, project, payload, execution=execution, run=run)
    return {"investigation": serialize_investigation(_investigation_for_project(db, project.id, investigation.id) or investigation), "reused": False}


@app.get("/v1/investigations")
def list_investigations(project: ProjectDep, db: Db, limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    investigations = db.scalars(select(DebugInvestigation).where(DebugInvestigation.project_id == project.id).order_by(DebugInvestigation.created_at.desc()).limit(limit)).all()
    return {"items": [serialize_investigation(_investigation_for_project(db, project.id, item.id) or item) for item in investigations]}


@app.get("/v1/investigations/{investigation_id}")
def get_investigation(investigation_id: str, project: ProjectDep, db: Db) -> dict[str, Any]:
    investigation = _investigation_for_project(db, project.id, investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    for attempt in investigation.reproductions:
        _sync_reproduction(db, attempt)
    for verification in investigation.verifications:
        _sync_verification(db, investigation, verification)
    db.commit()
    refreshed = _investigation_for_project(db, project.id, investigation_id)
    return serialize_investigation(refreshed or investigation)


@app.post("/v1/investigations/{investigation_id}/reproduction", status_code=202)
def start_reproduction(investigation_id: str, payload: ReproductionRequest, project: ProjectDep, db: Db) -> dict[str, Any]:
    investigation = _investigation_for_project(db, project.id, investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    if investigation.status in {"verified", "cancelled"}:
        raise HTTPException(status_code=409, detail=f"Investigation is already {investigation.status}.")
    original = _execution_for_project(db, project.id, investigation.original_execution_id) if investigation.original_execution_id else None
    attempt = ReproductionAttempt(
        investigation_id=investigation.id,
        original_execution_id=original.id if original else None,
        original_trace_id=investigation.original_trace_id,
        source_revision=investigation.source_revision,
        input_json=redact_value(payload.inputs if payload.inputs is not None else (original.input_json if original else {})),
        input_provenance_json={"kind": "request_override" if payload.inputs is not None else "original_execution", "original_execution_id": original.id if original else None},
        configuration_json={"analysis_id": investigation.analysis_id, "configuration_id": original.configuration_id if original else None},
        environment_json={"worker_image": settings.execution_worker_image, "timeout_seconds": original.timeout_seconds if original else settings.execution_timeout_seconds, "memory_mb": original.memory_mb if original else settings.execution_memory_mb},
        differences_json=[] if original else ["Required source snapshot, configuration, or original inputs are not linked to this trace."],
        status="pending" if original else "blocked",
    )
    db.add(attempt)
    db.flush()
    if not original:
        transition_investigation(investigation, "blocked") if investigation.status != "blocked" else None
        db.commit()
        return {"attempt": serialize_reproduction(attempt)}
    transition_investigation(investigation, "reproducing") if investigation.status in {"open", "inconclusive", "blocked"} else None
    attempt.status = "running"
    attempt.started_at = datetime.utcnow()
    db.commit()
    try:
        execution = _create_debug_execution(db, project, original, source_override_path=None, idempotency_key=f"debug-reproduction:{attempt.id}", input_value=payload.inputs)
    except Exception as exc:
        attempt.status = "blocked"
        attempt.completed_at = datetime.utcnow()
        attempt.result_json = {"error": "The reproduction could not be queued."}
        attempt.differences_json = [str(exc)[:500]]
        db.commit()
        return {"attempt": serialize_reproduction(attempt)}
    attempt.reproduction_execution_id = execution.id
    attempt.reproduction_trace_id = execution.trace_id
    db.commit()
    return {"attempt": serialize_reproduction(attempt), "execution": serialize_execution(execution)}


@app.post("/v1/investigations/{investigation_id}/regression-test", status_code=201)
def generate_regression_test(investigation_id: str, project: ProjectDep, db: Db) -> dict[str, Any]:
    investigation = _investigation_for_project(db, project.id, investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    existing = max(investigation.regression_tests, key=lambda item: item.created_at, default=None)
    if existing:
        return {"test": serialize_regression_test(existing), "reused": True}
    original = _execution_for_project(db, project.id, investigation.original_execution_id) if investigation.original_execution_id else None
    analysis = db.get(RepositoryAnalysis, investigation.analysis_id) if investigation.analysis_id else None
    definition = build_regression_test(analysis, original, investigation.id)
    if not definition:
        artifact = RegressionTestArtifact(investigation_id=investigation.id, source_revision=investigation.source_revision, file_path="unavailable", code="", description="A deterministic regression test could not be generated from the available source contract.", input_json=redact_value(original.input_json if original else {}), expected_json={}, source_evidence_json=[], assumptions_json=["A supported deterministic test template and source snapshot are required."], status="blocked", original_result_json={"status": "blocked", "reason": "Insufficient source evidence."}, patched_result_json={})
        db.add(artifact)
        if investigation.status not in {"blocked", "verified", "failed", "cancelled"}:
            transition_investigation(investigation, "blocked")
        db.commit()
        return {"test": serialize_regression_test(artifact)}
    source_root = Path(analysis.source_path).resolve()
    workspace = Path(settings.repository_storage_path).expanduser().resolve() / "investigations" / investigation.id / f"test-original-{uuid4().hex}"
    copy_isolated_snapshot(source_root, workspace)
    _write_generated_test(workspace, definition["file_path"], definition["code"])
    result = run_isolated_unittest(settings, workspace, definition["file_path"])
    result_text = str(result).lower()
    intended_failure = result.get("status") == "failed" and any(str(value).lower() in result_text for value in definition["expected_json"].values())
    status_value = "validated" if intended_failure else "rejected" if result.get("status") == "passed" or result.get("status") == "failed" else "blocked"
    artifact = RegressionTestArtifact(investigation_id=investigation.id, candidate_id=investigation.candidates[0].id if investigation.candidates else None, source_revision=investigation.source_revision, file_path=definition["file_path"], code=definition["code"], description=definition["description"], input_json=definition["input_json"], expected_json=definition["expected_json"], source_evidence_json=[serialize_candidate(investigation.candidates[0])] if investigation.candidates else [], assumptions_json=definition["assumptions"], workspace_path=str(workspace), status=status_value, original_result_json=redact_value(result), patched_result_json={})
    db.add(artifact)
    if status_value == "validated":
        transition_investigation(investigation, "test_generated") if investigation.status in {"open", "reproducing", "inconclusive", "blocked"} else None
    elif status_value == "rejected":
        transition_investigation(investigation, "inconclusive") if investigation.status in {"open", "reproducing", "blocked"} else None
    else:
        transition_investigation(investigation, "blocked") if investigation.status not in {"blocked", "verified", "failed", "cancelled"} else None
    db.commit()
    return {"test": serialize_regression_test(artifact), "reused": False}


@app.post("/v1/investigations/{investigation_id}/patch", status_code=201)
def propose_patch(investigation_id: str, project: ProjectDep, db: Db) -> dict[str, Any]:
    investigation = _investigation_for_project(db, project.id, investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    existing = max(investigation.patches, key=lambda item: item.created_at, default=None)
    if existing:
        return {"patch": serialize_patch(existing), "reused": True}
    artifact = max(investigation.regression_tests, key=lambda item: item.created_at, default=None)
    if not artifact or artifact.status != "validated":
        raise HTTPException(status_code=409, detail="Generate and validate a regression test against the original source before proposing a patch.")
    candidate = next((item for item in investigation.candidates if item.id == artifact.candidate_id), None) or (investigation.candidates[0] if investigation.candidates else None)
    analysis = db.get(RepositoryAnalysis, investigation.analysis_id) if investigation.analysis_id else None
    if not candidate or not analysis:
        raise HTTPException(status_code=409, detail="A source-linked root-cause candidate and immutable repository snapshot are required.")
    definition = generate_patch(analysis, candidate, artifact, investigation.id, settings.repository_storage_path)
    if not definition:
        raise HTTPException(status_code=422, detail="No deterministic evidence-backed patch is available for this source revision.")
    patch = ProposedPatch(investigation_id=investigation.id, candidate_id=candidate.id, regression_test_id=artifact.id, base_source_revision=investigation.source_revision, base_archive_fingerprint=investigation.archive_fingerprint, patch_text=definition["patch_text"], explanation=definition["explanation"], evidence_json=definition["evidence"], change_json=definition["changes"], workspace_path=definition["workspace_path"], status="pending_review")
    db.add(patch)
    transition_investigation(investigation, "patch_proposed") if investigation.status in {"test_generated", "open", "inconclusive"} else None
    db.commit()
    return {"patch": serialize_patch(patch), "reused": False}


@app.post("/v1/investigations/{investigation_id}/patches/{patch_id}/decision")
def decide_patch(investigation_id: str, patch_id: str, payload: PatchDecision, project: ProjectDep, db: Db) -> dict[str, Any]:
    investigation = _investigation_for_project(db, project.id, investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    patch = db.scalar(select(ProposedPatch).where(ProposedPatch.id == patch_id, ProposedPatch.investigation_id == investigation.id))
    if not patch:
        raise HTTPException(status_code=404, detail="Proposed patch not found.")
    if patch.status not in {"pending_review", "approved", "rejected"}:
        raise HTTPException(status_code=409, detail="This patch can no longer be reviewed.")
    patch.decision = payload.decision
    patch.decided_at = datetime.utcnow()
    patch.status = payload.decision
    if payload.decision == "rejected" and investigation.status == "patch_proposed":
        transition_investigation(investigation, "open")
    db.commit()
    return {"patch": serialize_patch(patch), "applied_to_original_repository": False, "message": "The decision is recorded. Source changes remain isolated and are never applied automatically."}


@app.post("/v1/investigations/{investigation_id}/verify", status_code=202)
def verify_investigation(investigation_id: str, payload: VerificationRequest, project: ProjectDep, db: Db) -> dict[str, Any]:
    investigation = _investigation_for_project(db, project.id, investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    patch = max(investigation.patches, key=lambda item: item.created_at, default=None)
    artifact = max(investigation.regression_tests, key=lambda item: item.created_at, default=None)
    original = _execution_for_project(db, project.id, investigation.original_execution_id) if investigation.original_execution_id else None
    if not patch or not artifact:
        raise HTTPException(status_code=409, detail="A proposed patch and generated regression test are required before verification.")
    if artifact.status != "validated":
        raise HTTPException(status_code=409, detail="The regression test did not validate the original failure; verification cannot proceed.")
    if not original:
        verification = VerificationRun(investigation_id=investigation.id, patch_id=patch.id, regression_test_id=artifact.id, original_trace_id=investigation.original_trace_id, status="inconclusive", original_test_json=artifact.original_result_json or {}, patched_test_json={}, existing_tests_json={}, command_results_json=[], report_json={"reason": "The original trace has no controlled execution to rerun."}, error_message="Controlled rerun is unavailable for a trace-only investigation.")
        db.add(verification)
        transition_investigation(investigation, "inconclusive") if investigation.status not in {"inconclusive", "verified", "failed", "cancelled"} else None
        db.commit()
        return {"verification": serialize_verification(verification)}
    if not payload.run_controlled_rerun:
        raise HTTPException(status_code=422, detail="A controlled rerun is required to mark a fix verified.")
    if patch.status == "rejected":
        raise HTTPException(status_code=409, detail="The proposed patch was rejected and cannot be verified.")
    transition_investigation(investigation, "verifying") if investigation.status in {"patch_proposed", "open", "inconclusive", "blocked"} else None
    verification = VerificationRun(investigation_id=investigation.id, patch_id=patch.id, regression_test_id=artifact.id, original_execution_id=original.id, original_trace_id=investigation.original_trace_id, status="running", started_at=datetime.utcnow(), original_test_json={}, patched_test_json={}, existing_tests_json={}, command_results_json=[], report_json={})
    db.add(verification)
    db.commit()
    try:
        original_test = run_isolated_unittest(settings, artifact.workspace_path or "", artifact.file_path)
        patched_test = run_isolated_unittest(settings, patch.workspace_path or "", artifact.file_path)
        analysis = db.get(RepositoryAnalysis, investigation.analysis_id) if investigation.analysis_id else None
        existing_results: list[dict[str, Any]] = []
        if analysis and analysis.source_path and patch.workspace_path:
            for test_path in discover_existing_tests(Path(patch.workspace_path), artifact.file_path):
                existing_results.append({"file_path": test_path, "result": run_isolated_unittest(settings, patch.workspace_path, test_path)})
        existing_status = "passed" if existing_results and all(item["result"].get("status") == "passed" for item in existing_results) else "blocked" if not existing_results else "failed"
        verification.original_test_json = redact_value(original_test)
        verification.patched_test_json = redact_value(patched_test)
        verification.existing_tests_json = {"status": existing_status, "items": redact_value(existing_results)}
        verification.command_results_json = [
            {"kind": "original_regression", "file_path": artifact.file_path, "result": redact_value(original_test)},
            {"kind": "patched_regression", "file_path": artifact.file_path, "result": redact_value(patched_test)},
            {"kind": "existing_tests", "items": redact_value(existing_results)},
        ]
        artifact.patched_result_json = redact_value(patched_test)
        if original_test.get("status") != "failed":
            verification.status = "inconclusive"
            verification.error_message = "The regression test no longer fails against the original source; the captured defect was not revalidated."
            verification.completed_at = datetime.utcnow()
            verification.report_json = {"reason": verification.error_message, "original_test": redact_value(original_test)}
            transition_investigation(investigation, "inconclusive")
        elif patched_test.get("status") != "passed" or existing_status != "passed":
            verification.status = "failed" if patched_test.get("status") != "blocked" and existing_status != "blocked" else "blocked"
            verification.error_message = "The patched regression test or relevant existing tests did not pass."
            verification.completed_at = datetime.utcnow()
            verification.report_json = {"reason": verification.error_message}
            transition_investigation(investigation, verification.status)
        else:
            patched_execution = _create_debug_execution(db, project, original, source_override_path=patch.workspace_path, idempotency_key=f"debug-verification:{verification.id}", source_revision=f"{investigation.source_revision}:patch:{patch.id}")
            verification.patched_execution_id = patched_execution.id
            verification.patched_trace_id = patched_execution.trace_id
            _sync_verification(db, investigation, verification)
        db.commit()
    except Exception as exc:
        verification.status = "blocked"
        verification.error_message = str(exc)[:1000]
        verification.completed_at = datetime.utcnow()
        transition_investigation(investigation, "blocked") if investigation.status == "verifying" else None
        db.commit()
    refreshed = _investigation_for_project(db, project.id, investigation_id)
    latest = max(refreshed.verifications, key=lambda item: item.created_at) if refreshed and refreshed.verifications else verification
    return {"verification": serialize_verification(latest)}


@app.post("/v1/executions/{execution_id}/cancel")
def cancel_execution(execution_id: str, payload: ExecutionCancel, project: ProjectDep, db: Db) -> dict[str, Any]:
    execution = _execution_for_project(db, project.id, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found.")
    if execution.status in {"succeeded", "failed", "timed_out", "cancelled", "infrastructure_error"}:
        return {"execution": serialize_execution(execution), "cancelled": False}
    if not execution_coordinator.request_cancel(execution_id):
        raise HTTPException(status_code=409, detail="Execution is no longer cancellable.")
    db.refresh(execution)
    return {"execution": serialize_execution(execution), "cancelled": True, "reason": payload.reason}


@app.post("/v1/executions/{execution_id}/events")
def ingest_execution_events(execution_id: str, payload: EventBatch, db: Db, x_execution_token: Annotated[str | None, Header(alias="X-Execution-Token")] = None) -> dict[str, Any]:
    if not x_execution_token:
        raise HTTPException(status_code=401, detail="Execution token is required.")
    execution = db.scalar(select(ExecutionRun).where(ExecutionRun.id == execution_id, ExecutionRun.execution_token_hash == token_hash(x_execution_token)))
    if not execution:
        raise HTTPException(status_code=401, detail="Invalid execution token.")
    if execution.status in {"succeeded", "failed", "timed_out", "cancelled", "infrastructure_error"}:
        raise HTTPException(status_code=409, detail="The execution is already terminal.")
    project = db.get(Project, execution.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Execution project not found.")
    return _ingest_events(payload, project, db, expected_trace_id=execution.trace_id)


@app.post("/v1/repositories/{analysis_id}/executions", status_code=202)
def create_execution(analysis_id: str, payload: ExecutionCreate, project: ProjectDep, db: Db) -> dict[str, Any]:
    analysis = load_analysis(db, project.id, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Repository analysis not found.")
    if analysis.status not in {"analysis_complete", "partially_analyzed"} or not analysis.source_path:
        raise HTTPException(status_code=409, detail="This repository analysis has no executable source snapshot.")
    finding = next((item for item in analysis.findings if item.stable_id == payload.workflow_entry_point_id), None)
    if not finding or finding.kind != "workflow_entry":
        raise HTTPException(status_code=422, detail="Select a discovered workflow entry point.")
    configuration = next((item for item in analysis.configurations if item.id == payload.configuration_id), None)
    if not configuration or configuration.project_id != project.id:
        raise HTTPException(status_code=404, detail="Instrumentation configuration not found for this analysis.")
    if not configuration.valid or configuration.stale:
        raise HTTPException(status_code=409, detail="The selected instrumentation configuration is invalid or stale. Save a configuration for the current source revision.")
    config_source = (configuration.config_json or {}).get("source", {})
    if config_source.get("archive_fingerprint") != analysis.archive_fingerprint or config_source.get("source_revision") != analysis.source_revision:
        raise HTTPException(status_code=409, detail="The selected instrumentation configuration belongs to a different source revision.")
    selected_entries = {str(item.get("finding_id")) for item in (configuration.config_json or {}).get("workflow_entry_points", []) if isinstance(item, dict)}
    if finding.stable_id not in selected_entries:
        raise HTTPException(status_code=422, detail="The selected workflow entry point is not included in the instrumentation configuration.")
    if not finding.file_path.endswith(".py") or not finding.symbol_name:
        raise HTTPException(status_code=422, detail="Only discovered Python function entry points are supported by the controlled execution MVP.")
    try:
        encoded_input = json.dumps(payload.inputs, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Workflow inputs must be JSON-serializable.") from exc
    if len(encoded_input) > settings.execution_input_bytes:
        raise HTTPException(status_code=413, detail="Workflow inputs exceed the configured execution limit.")
    default_key = hashlib.sha256(f"{analysis.id}:{configuration.id}:{finding.stable_id}:{analysis.source_revision}:".encode() + encoded_input).hexdigest()
    idempotency_key = payload.idempotency_key or default_key
    existing = db.scalar(select(ExecutionRun).where(ExecutionRun.project_id == project.id, ExecutionRun.idempotency_key == idempotency_key))
    if existing:
        return {"execution": serialize_execution(existing), "reused": True}
    raw_token = execution_token()
    execution = ExecutionRun(
        project_id=project.id,
        analysis_id=analysis.id,
        configuration_id=configuration.id,
        source_revision=analysis.source_revision,
        archive_fingerprint=analysis.archive_fingerprint,
        entry_finding_id=finding.stable_id,
        entry_file_path=finding.file_path,
        entry_symbol=finding.symbol_name,
        trace_id=uuid4().hex,
        idempotency_key=idempotency_key,
        status="queued",
        input_json=redact_value(payload.inputs),
        input_fingerprint=input_fingerprint(payload.inputs),
        execution_token_hash=token_hash(raw_token),
        execution_token_prefix=raw_token[:16],
        result_json={},
        logs_text="",
        timeout_seconds=settings.execution_timeout_seconds,
        memory_mb=settings.execution_memory_mb,
        cpu_limit=str(settings.execution_cpu_limit),
        pids_limit=settings.execution_pids_limit,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    execution_coordinator.submit(execution.id, raw_token, payload.inputs)
    return {"execution": serialize_execution(execution), "reused": False}


@app.get("/v1/executions/{execution_id}/trace")
def get_execution_trace(execution_id: str, project: ProjectDep, db: Db) -> dict[str, Any]:
    execution = _execution_for_project(db, project.id, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found.")
    if not db.scalar(select(Run).where(Run.project_id == project.id, Run.trace_id == execution.trace_id)):
        raise HTTPException(status_code=404, detail="Execution trace is not available yet.")
    return get_run(execution.trace_id, project, db)


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
