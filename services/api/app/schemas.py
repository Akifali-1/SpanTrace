from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


EventStatus = Literal["running", "succeeded", "failed", "cancelled", "unknown"]


class TraceEventIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0"
    event_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    span_id: str | None = Field(default=None, max_length=128)
    parent_span_id: str | None = Field(default=None, max_length=128)
    agent_name: str | None = Field(default=None, max_length=160)
    event_type: str = Field(min_length=1, max_length=64)
    kind: str = Field(default="workflow", max_length=64)
    status: EventStatus = "running"
    occurred_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    input: Any | None = None
    output: Any | None = None
    tool_name: str | None = Field(default=None, max_length=160)
    tool_args: Any | None = None
    tool_result: Any | None = None
    handoff_to: str | None = Field(default=None, max_length=160)
    error_type: str | None = Field(default=None, max_length=160)
    error_details: str | None = Field(default=None, max_length=10_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def normalize_event_type(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")


class EventBatch(BaseModel):
    events: list[TraceEventIn] = Field(min_length=1, max_length=500)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class KeyCreate(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=120)


class RegressionCaseCreate(BaseModel):
    name: str = Field(default="Approval invariant regression", min_length=1, max_length=200)


class RegressionRunRequest(BaseModel):
    fixed: bool = False


def event_dict(event: TraceEventIn) -> dict[str, Any]:
    data = event.model_dump()
    data["input_json"] = data.pop("input")
    data["output_json"] = data.pop("output")
    data["metadata_json"] = data.pop("metadata")
    return data
