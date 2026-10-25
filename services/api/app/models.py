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
