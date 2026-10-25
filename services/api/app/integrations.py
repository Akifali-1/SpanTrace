from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Project, Run, TraceEvent


SUPPORTED_INTEGRATIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "opentelemetry",
        "name": "OpenTelemetry spans",
        "tested_versions": ["opentelemetry-api 1.29.0", "opentelemetry-sdk 1.29.0"],
        "event_types": ["run_started", "run_completed", "agent_span", "node_completed", "model_call", "tool_call", "handoff", "exception"],
        "install": "pip install opentelemetry-api==1.29.0 opentelemetry-sdk==1.29.0",
        "activation": "provider, adapter = scope.instrument_opentelemetry(service_name='my-workflow')",
        "notes": "Captures completed spans emitted through the public OpenTelemetry SDK. Framework-specific details are available only when the framework exposes them as span attributes or events.",
    },
    {
        "id": "callback",
        "name": "Framework callback adapter",
        "tested_versions": ["SpanTrace callback contract 1.1"],
        "event_types": ["run_started", "run_completed", "node_started", "node_completed", "model_call", "tool_call", "handoff", "retry", "exception"],
        "install": "No framework package required; use the framework's supported callback/listener API.",
        "activation": "adapter = CallbackAdapter(scope, framework='your-framework')",
        "notes": "Use when a framework exposes lifecycle callbacks but does not emit OpenTelemetry spans. Unsupported internal events remain explicitly unavailable.",
    },
)


def _state(events: list[TraceEvent]) -> str:
    if not events:
        return "no_events_received"
    event_types = {event.event_type for event in events}
    uncertain = any(event.relationship_confidence in {"unknown", "inferred"} for event in events)
    if "run_started" not in event_types or "run_completed" not in event_types or uncertain:
        return "partially_observed"
    return "events_received"


def diagnostics_for_project(db: Session, project: Project) -> list[dict[str, Any]]:
    events = db.scalars(select(TraceEvent).join(Run).where(Run.project_id == project.id).order_by(TraceEvent.occurred_at.desc())).all()
    result: list[dict[str, Any]] = []
    for definition in SUPPORTED_INTEGRATIONS:
        observed = [event for event in events if event.integration == definition["id"]]
        latest = observed[0].occurred_at if observed else None
        result.append(
            {
                **definition,
                "state": _state(observed),
                "events_received": len(observed),
                "run_count": len({event.run_id for event in observed}),
                "last_ingestion_at": latest.isoformat() + "Z" if latest else None,
                "captured_event_types": sorted({event.event_type for event in observed}),
                "redaction": "Payloads are redacted before export; input/output capture is separately configurable.",
                "evidence": "telemetry" if observed else "none",
                "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
    return result
