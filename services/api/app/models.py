from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship as orm_relationship

from .db import Base

JSONType = JSON


def new_uuid() -> str:
    return str(uuid4())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    keys: Mapped[list["ApiKey"]] = orm_relationship(back_populates="project", cascade="all, delete-orphan")
    runs: Mapped[list["Run"]] = orm_relationship(back_populates="project", cascade="all, delete-orphan")
    repository_analyses: Mapped[list["RepositoryAnalysis"]] = orm_relationship(back_populates="project", cascade="all, delete-orphan")
    execution_runs: Mapped[list["ExecutionRun"]] = orm_relationship(back_populates="project", cascade="all, delete-orphan")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="default")
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(16))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    project: Mapped[Project] = orm_relationship(back_populates="keys")


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("project_id", "trace_id", name="uq_project_trace"), Index("ix_runs_project_started", "project_id", "started_at"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    trace_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    project: Mapped[Project] = orm_relationship(back_populates="runs")
    events: Mapped[list["TraceEvent"]] = orm_relationship(back_populates="run", cascade="all, delete-orphan", order_by="TraceEvent.occurred_at")


class TraceEvent(Base):
    __tablename__ = "trace_events"
    __table_args__ = (UniqueConstraint("project_id", "event_id", name="uq_project_event"), Index("ix_events_run_time", "run_id", "occurred_at"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(String(128))
    span_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parent_span_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(64), default="workflow")
    status: Mapped[str] = mapped_column(String(32), default="running")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_json: Mapped[Any | None] = mapped_column(JSONType, nullable=True)
    output_json: Mapped[Any | None] = mapped_column(JSONType, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    tool_args: Mapped[Any | None] = mapped_column(JSONType, nullable=True)
    tool_result: Mapped[Any | None] = mapped_column(JSONType, nullable=True)
    handoff_to: Mapped[str | None] = mapped_column(String(160), nullable=True)
    integration: Mapped[str] = mapped_column(String(80), default="manual")
    framework: Mapped[str | None] = mapped_column(String(120), nullable=True)
    framework_run_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    framework_parent_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    relationship: Mapped[str] = mapped_column(String(64), default="observed")
    relationship_confidence: Mapped[str] = mapped_column(String(32), default="observed")
    error_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    schema_version: Mapped[str] = mapped_column(String(16), default="1.0")
    run: Mapped[Run] = orm_relationship(back_populates="events")


class RegressionCase(Base):
    __tablename__ = "regression_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    source_trace_id: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(200))
    scenario: Mapped[dict[str, Any]] = mapped_column(JSONType)
    expected_assertions: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())


class RegressionRun(Base):
    __tablename__ = "regression_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("regression_cases.id", ondelete="CASCADE"), index=True)
    passed: Mapped[bool] = mapped_column(default=False)
    actual: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())


class RepositoryAnalysis(Base):
    __tablename__ = "repository_analyses"
    __table_args__ = (Index("ix_repository_analyses_project_created", "project_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    source_kind: Mapped[str] = mapped_column(String(32))
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_revision: Mapped[str] = mapped_column(String(200))
    archive_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="waiting_for_source")
    analysis_version: Mapped[int] = mapped_column(Integer, default=1)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    limitations_json: Mapped[list[str]] = mapped_column(JSONType, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    project: Mapped[Project] = orm_relationship(back_populates="repository_analyses")
    findings: Mapped[list["RepositoryFinding"]] = orm_relationship(back_populates="analysis", cascade="all, delete-orphan")
    relationships: Mapped[list["RepositoryRelationship"]] = orm_relationship(back_populates="analysis", cascade="all, delete-orphan")
    configurations: Mapped[list["InstrumentationConfig"]] = orm_relationship(back_populates="analysis", cascade="all, delete-orphan")
    execution_runs: Mapped[list["ExecutionRun"]] = orm_relationship(back_populates="analysis", cascade="all, delete-orphan")


class RepositoryFinding(Base):
    __tablename__ = "repository_findings"
    __table_args__ = (UniqueConstraint("analysis_id", "stable_id", name="uq_repository_finding_stable"), Index("ix_repository_findings_analysis_kind", "analysis_id", "kind"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("repository_analyses.id", ondelete="CASCADE"), index=True)
    stable_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(48))
    name: Mapped[str] = mapped_column(String(240))
    symbol_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    symbol_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    framework: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detection_method: Mapped[str] = mapped_column(String(160))
    evidence_summary: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(48))
    instrumentation_status: Mapped[str] = mapped_column(String(48), default="needs_confirmation")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    analysis: Mapped[RepositoryAnalysis] = orm_relationship(back_populates="findings")
    outgoing_relationships: Mapped[list["RepositoryRelationship"]] = orm_relationship(foreign_keys="RepositoryRelationship.source_finding_id", back_populates="source_finding")
    incoming_relationships: Mapped[list["RepositoryRelationship"]] = orm_relationship(foreign_keys="RepositoryRelationship.target_finding_id", back_populates="target_finding")


class RepositoryRelationship(Base):
    __tablename__ = "repository_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("repository_analyses.id", ondelete="CASCADE"), index=True)
    source_finding_id: Mapped[str] = mapped_column(ForeignKey("repository_findings.id", ondelete="CASCADE"), index=True)
    target_finding_id: Mapped[str | None] = mapped_column(ForeignKey("repository_findings.id", ondelete="CASCADE"), nullable=True, index=True)
    target_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    relationship_type: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[str] = mapped_column(String(48))
    detection_method: Mapped[str] = mapped_column(String(160))
    evidence_summary: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(String(500))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    analysis: Mapped[RepositoryAnalysis] = orm_relationship(back_populates="relationships")
    source_finding: Mapped[RepositoryFinding] = orm_relationship(foreign_keys=[source_finding_id], back_populates="outgoing_relationships")
    target_finding: Mapped[RepositoryFinding | None] = orm_relationship(foreign_keys=[target_finding_id], back_populates="incoming_relationships")


class InstrumentationConfig(Base):
    __tablename__ = "instrumentation_configs"
    __table_args__ = (UniqueConstraint("analysis_id", "version", name="uq_instrumentation_config_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("repository_analyses.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONType)
    valid: Mapped[bool] = mapped_column(default=True)
    stale: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    analysis: Mapped[RepositoryAnalysis] = orm_relationship(back_populates="configurations")
    execution_runs: Mapped[list["ExecutionRun"]] = orm_relationship(back_populates="configuration")


class ExecutionRun(Base):
    __tablename__ = "execution_runs"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_execution_project_idempotency"),
        Index("ix_execution_runs_project_created", "project_id", "created_at"),
        Index("ix_execution_runs_project_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("repository_analyses.id", ondelete="CASCADE"), index=True)
    configuration_id: Mapped[str] = mapped_column(ForeignKey("instrumentation_configs.id", ondelete="CASCADE"), index=True)
    source_revision: Mapped[str] = mapped_column(String(200))
    archive_fingerprint: Mapped[str] = mapped_column(String(64))
    entry_finding_id: Mapped[str] = mapped_column(String(64))
    entry_file_path: Mapped[str] = mapped_column(String(500))
    entry_symbol: Mapped[str] = mapped_column(String(240))
    trace_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    worker_container_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    execution_token_hash: Mapped[str] = mapped_column(String(64))
    execution_token_prefix: Mapped[str] = mapped_column(String(16))
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    logs_text: Mapped[str] = mapped_column(Text, default="")
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    memory_mb: Mapped[int] = mapped_column(Integer)
    cpu_limit: Mapped[str] = mapped_column(String(32))
    pids_limit: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    project: Mapped[Project] = orm_relationship(back_populates="execution_runs")
    analysis: Mapped[RepositoryAnalysis] = orm_relationship(back_populates="execution_runs")
    configuration: Mapped[InstrumentationConfig] = orm_relationship(back_populates="execution_runs")
