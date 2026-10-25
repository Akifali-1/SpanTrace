from __future__ import annotations

import contextvars
import functools
import json
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4


_current_trace: contextvars.ContextVar[Trace | None] = contextvars.ContextVar("agentscope_trace", default=None)
_current_span: contextvars.ContextVar[Span | None] = contextvars.ContextVar("agentscope_span", default=None)


SENSITIVE_KEYS = {"password", "passwd", "secret", "token", "api_key", "authorization", "cookie", "card_number"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def default_redactor(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else default_redactor(item) for key, item in value.items()}
    if isinstance(value, list):
        return [default_redactor(item) for item in value]
    if isinstance(value, tuple):
        return [default_redactor(item) for item in value]
    return value


class AgentScope:
    def __init__(
        self,
        api_key: str | None,
        endpoint: str = "http://localhost:8070",
        project_id: str | None = None,
        *,
        capture_payloads: bool = True,
        strict: bool = False,
        batch_size: int = 20,
        timeout: float = 5.0,
        redactor: Callable[[Any], Any] | None = None,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.project_id = project_id
        self.capture_payloads = capture_payloads
        self.strict = strict
        self.batch_size = max(1, batch_size)
        self.timeout = timeout
        self.redactor = redactor or default_redactor
        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.RLock()
        self.last_error: Exception | None = None
        self.disabled = not bool(api_key)

    @classmethod
    def from_env(cls, **overrides: Any) -> "AgentScope":
        capture = os.getenv("AGENTSCOPE_CAPTURE_PAYLOADS", "true").lower() not in {"0", "false", "no"}
        strict = os.getenv("AGENTSCOPE_STRICT", "false").lower() in {"1", "true", "yes"}
        return cls(
            api_key=os.getenv("AGENTSCOPE_API_KEY"),
            endpoint=os.getenv("AGENTSCOPE_API_URL", "http://localhost:8070"),
            project_id=os.getenv("AGENTSCOPE_PROJECT_ID"),
            capture_payloads=capture,
            strict=strict,
            batch_size=int(os.getenv("AGENTSCOPE_BATCH_SIZE", "20")),
            timeout=float(os.getenv("AGENTSCOPE_TIMEOUT", "5")),
            **overrides,
        )

    def trace(self, name: str, *, trace_id: str | None = None, metadata: dict[str, Any] | None = None) -> "Trace":
        return Trace(self, name, trace_id=trace_id, metadata=metadata)

    def instrument(self, name: str, *, kind: str = "agent"):
        def decorator(function):
            @functools.wraps(function)
            def wrapped(*args, **kwargs):
                trace = _current_trace.get()
                if trace is None:
                    return function(*args, **kwargs)
                with trace.span(name, kind=kind, input={"args": args, "kwargs": kwargs}) as span:
                    result = function(*args, **kwargs)
                    span.set_output(result)
                    return result

            return wrapped

        return decorator

    def _prepare(self, value: Any) -> Any:
        if not self.capture_payloads:
            return {"captured": False} if value is not None else None
        try:
            return self.redactor(value)
        except Exception:
            return "[UNSERIALIZABLE]"

    def _queue(self, event: dict[str, Any]) -> None:
        if self.disabled:
            return
        event["input"] = self._prepare(event.get("input"))
        event["output"] = self._prepare(event.get("output"))
        event["tool_args"] = self._prepare(event.get("tool_args"))
        event["tool_result"] = self._prepare(event.get("tool_result"))
        with self._lock:
            self._buffer.append(event)
            if len(self._buffer) >= self.batch_size:
                self.flush()

    def flush(self) -> None:
        if self.disabled:
            return
        with self._lock:
            if not self._buffer:
                return
            batch = list(self._buffer)
        payload = json.dumps({"events": batch}, default=str).encode("utf-8")
        request = urllib.request.Request(
            f"{self.endpoint}/v1/ingest/events",
            data=payload,
            headers={"Content-Type": "application/json", "X-API-Key": self.api_key or ""},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status >= 300:
                    raise RuntimeError(f"AgentScope ingestion returned HTTP {response.status}")
            with self._lock:
                del self._buffer[: len(batch)]
            self.last_error = None
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
            self.last_error = exc
            if self.strict:
                raise RuntimeError("AgentScope could not submit trace events") from exc

    def shutdown(self) -> None:
        self.flush()

    close = shutdown


class Trace:
    def __init__(self, scope: AgentScope, name: str, *, trace_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        self.scope = scope
        self.name = name
        self.trace_id = trace_id or str(uuid4())
        self.metadata = dict(metadata or {})
        self.metadata.setdefault("run_name", name)
        self.started_at = _utc_now()
        self._trace_token = None
        self._span_token = None

    def __enter__(self) -> "Trace":
        self._trace_token = _current_trace.set(self)
        self._span_token = _current_span.set(None)
        self.record("run_started", kind="workflow", status="running", metadata=self.metadata)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        status = "failed" if exc else "succeeded"
        if exc:
            self.record(
                "exception",
                kind="exception",
                status="failed",
                error_type=type(exc).__name__,
                error_details=str(exc),
            )
        self.record("run_completed", kind="workflow", status=status, ended_at=_utc_now(), metadata=self.metadata)
        if self._span_token is not None:
            _current_span.reset(self._span_token)
        if self._trace_token is not None:
            _current_trace.reset(self._trace_token)
        self.scope.flush()
        return False

    def span(self, name: str, *, kind: str = "agent", input: Any = None, metadata: dict[str, Any] | None = None) -> "Span":
        return Span(self, name, kind=kind, input=input, metadata=metadata)

    def tool(self, name: str, *, args: Any = None, metadata: dict[str, Any] | None = None) -> "Span":
        return Span(self, name, kind="tool", event_type="tool_call", tool_name=name, tool_args=args, metadata=metadata)

    def handoff(self, to_agent: str, *, from_agent: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        current = _current_span.get()
        self.record(
            "handoff",
            kind="handoff",
            status="succeeded",
            agent_name=from_agent or (current.name if current else None),
            parent_span_id=current.span_id if current else None,
            handoff_to=to_agent,
            metadata=metadata,
        )

    def record(self, event_type: str, *, kind: str = "workflow", status: str = "succeeded", **fields: Any) -> None:
        current = _current_span.get()
        occurred_at = fields.pop("occurred_at", None) or _utc_now()
        ended_at = fields.pop("ended_at", None)
        event = {
            "schema_version": "1.0",
            "event_id": str(uuid4()),
            "trace_id": self.trace_id,
            "span_id": fields.pop("span_id", None) or (current.span_id if event_type == "exception" and current else str(uuid4())),
            "parent_span_id": fields.pop("parent_span_id", None) if "parent_span_id" in fields else (current.span_id if current and event_type not in {"run_started", "run_completed"} else None),
            "agent_name": fields.pop("agent_name", None),
            "event_type": event_type,
            "kind": kind,
            "status": status,
            "occurred_at": _iso(occurred_at),
            "ended_at": _iso(ended_at) if ended_at else None,
            "duration_ms": fields.pop("duration_ms", None),
            "input": fields.pop("input", None),
            "output": fields.pop("output", None),
            "tool_name": fields.pop("tool_name", None),
            "tool_args": fields.pop("tool_args", None),
            "tool_result": fields.pop("tool_result", None),
            "handoff_to": fields.pop("handoff_to", None),
            "error_type": fields.pop("error_type", None),
            "error_details": fields.pop("error_details", None),
            "metadata": fields.pop("metadata", None) or {},
        }
        self.scope._queue(event)


class Span:
    def __init__(self, trace: Trace, name: str, *, kind: str, event_type: str | None = None, input: Any = None, tool_name: str | None = None, tool_args: Any = None, metadata: dict[str, Any] | None = None) -> None:
        self.trace = trace
        self.scope = trace.scope
        self.name = name
        self.kind = kind
        self.event_type = event_type or ("agent_span" if kind == "agent" else f"{kind}_span")
        self.input = input
        self.output: Any = None
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.tool_result: Any = None
        self.metadata = metadata or {}
        self.span_id = str(uuid4())
        self.parent_span_id: str | None = None
        self.started_at: datetime | None = None
        self._token = None

    def __enter__(self) -> "Span":
        parent = _current_span.get()
        self.parent_span_id = parent.span_id if parent else None
        self.started_at = _utc_now()
        self._token = _current_span.set(self)
        return self

    def set_output(self, value: Any) -> None:
        if self.kind == "tool":
            self.tool_result = value
        else:
            self.output = value

    def __exit__(self, exc_type, exc, tb) -> bool:
        ended_at = _utc_now()
        status = "failed" if exc else "succeeded"
        duration_ms = int((ended_at - (self.started_at or ended_at)).total_seconds() * 1000)
        self.trace.record(
            self.event_type,
            kind=self.kind,
            status=status,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            agent_name=self.name,
            input=self.input,
            output=self.output,
            tool_name=self.tool_name,
            tool_args=self.tool_args,
            tool_result=self.tool_result,
            metadata=self.metadata,
            occurred_at=self.started_at or ended_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            error_type=type(exc).__name__ if exc else None,
            error_details=str(exc) if exc else None,
        )
        if self._token is not None:
            _current_span.reset(self._token)
        return False
