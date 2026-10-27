from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Any, Iterator
from uuid import uuid4

from agentscope.client import Span, Trace, _current_trace
from spantrace import SpanTrace


def new_scope() -> SpanTrace:
    scope = SpanTrace(
        api_key=os.getenv("SPANTRACE_API_KEY") or os.getenv("SPANTRACE_EXECUTION_TOKEN") or os.getenv("AGENTSCOPE_API_KEY"),
        endpoint=os.getenv("SPANTRACE_API_URL") or os.getenv("AGENTSCOPE_API_URL", "http://localhost:8070"),
        project_id=os.getenv("SPANTRACE_PROJECT_ID") or os.getenv("AGENTSCOPE_PROJECT_ID"),
        strict=True,
        capture_payloads=True,
        batch_size=int(os.getenv("SPANTRACE_BATCH_SIZE", "100")),
        timeout=float(os.getenv("SPANTRACE_TIMEOUT", "5")),
        execution_id=os.getenv("SPANTRACE_EXECUTION_ID"),
        execution_token=os.getenv("SPANTRACE_EXECUTION_TOKEN"),
    )
    active = _current_trace.get()
    if active is not None:
        active.scope.batch_size = max(active.scope.batch_size, scope.batch_size)
    return scope


@contextmanager
def workflow_trace(scope: SpanTrace, name: str, metadata: dict[str, Any]) -> Iterator[Trace]:
    """Use the controlled worker's current trace when one is already active."""

    active = _current_trace.get()
    if active is not None:
        yield active
        return
    with scope.trace(name, metadata=metadata) as trace:
        yield trace


def handoff(
    trace: Trace,
    source: Span,
    target_name: str,
    *,
    target_span_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit a handoff for a real function call and preserve its target ID."""

    trace.record(
        "handoff",
        kind="handoff",
        status="succeeded",
        span_id=f"handoff:{uuid4().hex}",
        parent_span_id=source.span_id,
        agent_name=source.name,
        handoff_to=target_name,
        relationship="handoff",
        relationship_confidence="observed" if target_span_id else "unknown",
        metadata={"target_span_id": target_span_id, **(metadata or {})},
    )
