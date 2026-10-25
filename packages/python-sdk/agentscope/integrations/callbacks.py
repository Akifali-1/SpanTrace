from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..client import AgentScope


def _iso(value: datetime | None) -> str:
    value = value or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class CallbackAdapter:
    """Normalize framework callback events without monkey-patching application code.

    Frameworks with a callback or listener API can call these lifecycle methods
    from their supported hooks. The adapter preserves framework IDs and emits
    the same event contract as the manual SDK path.
    """

    name = "callback"

    def __init__(self, scope: AgentScope, *, framework: str, capture_payloads: bool | None = None) -> None:
        self.scope = scope
        self.framework = framework
        self.capture_payloads = scope.capture_payloads if capture_payloads is None else capture_payloads
        self.events_received = 0
        self.last_event_at: str | None = None
        self._trace_ids: set[str] = set()

    def _emit(
        self,
        event_type: str,
        *,
        trace_id: str,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        agent_name: str | None = None,
        kind: str = "workflow",
        status: str = "succeeded",
        occurred_at: datetime | None = None,
        ended_at: datetime | None = None,
        input: Any = None,
        output: Any = None,
        tool_name: str | None = None,
        tool_args: Any = None,
        tool_result: Any = None,
        handoff_to: str | None = None,
        error_type: str | None = None,
        error_details: str | None = None,
        framework_run_id: str | None = None,
        framework_parent_id: str | None = None,
        relationship: str = "observed",
        relationship_confidence: str = "observed",
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> str:
        occurred_at = occurred_at or datetime.now(timezone.utc)
        duration_ms = int((ended_at - occurred_at).total_seconds() * 1000) if ended_at else None
        self.scope.emit(
            {
                "schema_version": "1.1",
                "event_id": event_id or str(uuid4()),
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "agent_name": agent_name,
                "event_type": event_type,
                "kind": kind,
                "status": status,
                "occurred_at": _iso(occurred_at),
                "ended_at": _iso(ended_at) if ended_at else None,
                "duration_ms": duration_ms,
                "input": input,
                "output": output,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "tool_result": tool_result,
                "handoff_to": handoff_to,
                "error_type": error_type,
                "error_details": error_details,
                "integration": self.name,
                "framework": self.framework,
                "framework_run_id": framework_run_id,
                "framework_parent_id": framework_parent_id,
                "relationship": relationship,
                "relationship_confidence": relationship_confidence,
                "metadata": metadata or {},
            }
        )
        self.events_received += 1
        self.last_event_at = _iso(occurred_at)
        self._trace_ids.add(trace_id)
        return event_id or ""

    def workflow_started(self, *, trace_id: str, run_name: str, run_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        self._emit("run_started", trace_id=trace_id, span_id=run_id, agent_name=run_name, kind="workflow", status="running", framework_run_id=run_id, metadata={"run_name": run_name, **(metadata or {})}, event_id=f"{trace_id}:start")

    def workflow_completed(self, *, trace_id: str, run_name: str, run_id: str | None = None, status: str = "succeeded", started_at: datetime | None = None, ended_at: datetime | None = None, metadata: dict[str, Any] | None = None) -> None:
        self._emit("run_completed", trace_id=trace_id, span_id=run_id, agent_name=run_name, kind="workflow", status=status, occurred_at=ended_at, ended_at=ended_at, framework_run_id=run_id, metadata={"run_name": run_name, **(metadata or {})}, event_id=f"{trace_id}:complete")

    def node_started(self, *, trace_id: str, node_id: str, name: str, parent_id: str | None = None, input: Any = None, kind: str = "agent", run_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        self._emit("node_started", trace_id=trace_id, span_id=node_id, parent_span_id=parent_id, agent_name=name, kind=kind, status="running", input=input, framework_run_id=run_id, framework_parent_id=parent_id, metadata=metadata)

    def node_completed(self, *, trace_id: str, node_id: str, name: str, parent_id: str | None = None, output: Any = None, status: str = "succeeded", started_at: datetime | None = None, ended_at: datetime | None = None, kind: str = "agent", run_id: str | None = None, error_type: str | None = None, error_details: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        self._emit("node_completed", trace_id=trace_id, span_id=node_id, parent_span_id=parent_id, agent_name=name, kind=kind, status=status, output=output, occurred_at=started_at, ended_at=ended_at, framework_run_id=run_id, framework_parent_id=parent_id, error_type=error_type, error_details=error_details, metadata=metadata)

    def model_completed(self, *, trace_id: str, span_id: str, model_name: str, parent_id: str | None = None, input: Any = None, output: Any = None, status: str = "succeeded", started_at: datetime | None = None, ended_at: datetime | None = None, run_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        self._emit("model_call", trace_id=trace_id, span_id=span_id, parent_span_id=parent_id, agent_name=model_name, kind="model", status=status, input=input, output=output, occurred_at=started_at, ended_at=ended_at, framework_run_id=run_id, framework_parent_id=parent_id, metadata=metadata)

    def tool_completed(self, *, trace_id: str, span_id: str, tool_name: str, parent_id: str | None = None, args: Any = None, result: Any = None, status: str = "succeeded", started_at: datetime | None = None, ended_at: datetime | None = None, run_id: str | None = None, metadata: dict[str, Any] | None = None, error_type: str | None = None, error_details: str | None = None) -> None:
        self._emit("tool_call", trace_id=trace_id, span_id=span_id, parent_span_id=parent_id, agent_name=tool_name, kind="tool", status=status, tool_name=tool_name, tool_args=args, tool_result=result, occurred_at=started_at, ended_at=ended_at, framework_run_id=run_id, framework_parent_id=parent_id, metadata=metadata, error_type=error_type, error_details=error_details)

    def handoff(self, *, trace_id: str, source_span_id: str | None, from_agent: str, to_agent: str, target_span_id: str | None = None, run_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        self._emit("handoff", trace_id=trace_id, span_id=f"handoff:{uuid4()}", parent_span_id=source_span_id, agent_name=from_agent, kind="handoff", handoff_to=to_agent, framework_run_id=run_id, framework_parent_id=source_span_id, relationship="handoff", relationship_confidence="observed" if target_span_id else "unknown", metadata={"target_span_id": target_span_id, **(metadata or {})})

    def retry(self, *, trace_id: str, span_id: str, operation: str, attempt: int, parent_id: str | None = None, run_id: str | None = None) -> None:
        self._emit("retry", trace_id=trace_id, span_id=span_id, parent_span_id=parent_id, agent_name=operation, kind="retry", framework_run_id=run_id, framework_parent_id=parent_id, metadata={"operation": operation, "attempt": attempt})

    def exception(self, *, trace_id: str, span_id: str | None, error_type: str, error_details: str, parent_id: str | None = None, run_id: str | None = None) -> None:
        self._emit("exception", trace_id=trace_id, span_id=span_id, parent_span_id=parent_id, kind="exception", status="failed", framework_run_id=run_id, framework_parent_id=parent_id, error_type=error_type, error_details=error_details)

    def diagnostics(self) -> dict[str, Any]:
        return {
            "integration": self.name,
            "framework": self.framework,
            "events_received": self.events_received,
            "trace_count": len(self._trace_ids),
            "last_event_at": self.last_event_at,
            "capture_payloads": self.capture_payloads,
        }
