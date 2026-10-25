from datetime import datetime
from typing import Any


def iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def serialize_event(event: Any) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "trace_id": event.run.trace_id if event.run else None,
        "span_id": event.span_id,
        "parent_span_id": event.parent_span_id,
        "agent_name": event.agent_name,
        "event_type": event.event_type,
        "kind": event.kind,
        "status": event.status,
        "occurred_at": iso(event.occurred_at),
        "ended_at": iso(event.ended_at),
        "duration_ms": event.duration_ms,
        "input": event.input_json,
        "output": event.output_json,
        "tool_name": event.tool_name,
        "model_name": event.model_name,
        "tool_args": event.tool_args,
        "tool_result": event.tool_result,
        "handoff_to": event.handoff_to,
        "integration": event.integration,
        "framework": event.framework,
        "framework_run_id": event.framework_run_id,
        "framework_parent_id": event.framework_parent_id,
        "relationship": event.relationship,
        "relationship_confidence": event.relationship_confidence,
        "error_type": event.error_type,
        "error_details": event.error_details,
        "metadata": event.metadata_json or {},
        "schema_version": event.schema_version,
    }


def serialize_run(run: Any, incidents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "trace_id": run.trace_id,
        "name": run.name,
        "status": run.status,
        "started_at": iso(run.started_at),
        "ended_at": iso(run.ended_at),
        "duration_ms": run.duration_ms,
        "event_count": run.event_count,
        "metadata": run.metadata_json or {},
        "incidents": incidents or [],
    }
