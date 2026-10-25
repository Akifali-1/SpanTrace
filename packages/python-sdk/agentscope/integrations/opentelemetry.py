from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from ..client import AgentScope

try:  # Keep the base SDK importable without the optional integration.
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

    OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by the optional-dependency test
    Resource = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment]
    BatchSpanProcessor = None  # type: ignore[assignment]
    OTEL_AVAILABLE = False

    class SpanExporter:  # type: ignore[no-redef]
        pass

    class SpanExportResult:  # type: ignore[no-redef]
        SUCCESS = "success"
        FAILURE = "failure"


def _iso_nanos(value: int | None) -> str:
    if not value:
        value = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
    return datetime.fromtimestamp(value / 1_000_000_000, timezone.utc).isoformat().replace("+00:00", "Z")


def _span_id(value: Any) -> str | None:
    if value is None:
        return None
    value = getattr(value, "span_id", value)
    try:
        number = int(value)
    except (TypeError, ValueError):
        return str(value)
    return None if number == 0 else f"{number:016x}"


def _trace_id(value: Any) -> str:
    value = getattr(value, "trace_id", value)
    try:
        return f"{int(value):032x}"
    except (TypeError, ValueError):
        return str(value)


def _json_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple, str, int, float, bool)) or value is None:
        return value
    return str(value)


def _attribute(attributes: Any, *names: str) -> Any:
    for name in names:
        if attributes and name in attributes:
            return attributes[name]
    return None


def _parse_payload(value: Any) -> Any:
    if not isinstance(value, str):
        return _json_value(value)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


class SpanTraceSpanExporter(SpanExporter):
    """OpenTelemetry exporter that normalizes completed spans into SpanTrace events."""

    def __init__(self, scope: AgentScope, *, framework: str = "opentelemetry") -> None:
        self.scope = scope
        self.framework = framework
        self.events_exported = 0
        self.last_export_at: str | None = None
        self._roots_seen: set[str] = set()

    def _emit(self, event: dict[str, Any]) -> None:
        self.scope.emit(event)
        self.events_exported += 1
        self.last_export_at = _iso_nanos(None)

    def export(self, spans: Iterable[Any]) -> SpanExportResult:
        try:
            for span in spans:
                self._export_span(span)
            return SpanExportResult.SUCCESS
        except Exception as exc:  # telemetry must not break the instrumented app
            self.scope.last_error = exc
            return SpanExportResult.FAILURE

    def _export_span(self, span: Any) -> None:
        context = span.context
        trace_id = _trace_id(context)
        span_id = _span_id(context)
        parent_span_id = _span_id(getattr(span, "parent", None))
        attributes = dict(getattr(span, "attributes", {}) or {})
        start = _iso_nanos(getattr(span, "start_time", None))
        end = _iso_nanos(getattr(span, "end_time", None))
        duration_ms = max(0, int(((getattr(span, "end_time", 0) or 0) - (getattr(span, "start_time", 0) or 0)) / 1_000_000))
        name = str(getattr(span, "name", "otel-span"))
        kind = str(_attribute(attributes, "spantrace.kind") or "agent")
        event_type = str(_attribute(attributes, "spantrace.event_type") or ("tool_call" if kind == "tool" else "model_call" if kind == "model" else "agent_span"))
        status_object = getattr(getattr(span, "status", None), "status_code", None)
        status_name = getattr(status_object, "name", str(status_object or "OK"))
        status = "failed" if "ERROR" in status_name else "succeeded"
        error_details = getattr(getattr(span, "status", None), "description", None)
        framework_run_id = _attribute(attributes, "spantrace.framework_run_id", "gen_ai.conversation.id")
        relationship = str(_attribute(attributes, "spantrace.relationship") or "observed")
        confidence = str(_attribute(attributes, "spantrace.relationship_confidence") or "observed")
        metadata = {
            "run_name": name if parent_span_id is None else None,
            "otel_span_name": name,
            "otel_attributes": {
                str(key): _json_value(value)
                for key, value in attributes.items()
                if not any(
                    str(key).startswith(prefix)
                    for prefix in (
                        "spantrace.input",
                        "spantrace.output",
                        "spantrace.tool_args",
                        "spantrace.tool_result",
                        "gen_ai.prompt",
                        "gen_ai.completion",
                        "gen_ai.response",
                        "gen_ai.input.messages",
                        "gen_ai.output.messages",
                    )
                )
            },
        }
        event = {
            "schema_version": "1.1",
            "event_id": f"otel:{trace_id}:{span_id or name}",
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "agent_name": str(_attribute(attributes, "spantrace.agent_name") or name),
            "event_type": event_type,
            "kind": kind,
            "status": status,
            "occurred_at": start,
            "ended_at": end,
            "duration_ms": duration_ms,
            "input": _parse_payload(_attribute(attributes, "spantrace.input")),
            "output": _parse_payload(_attribute(attributes, "spantrace.output")),
            "tool_name": _attribute(attributes, "spantrace.tool_name", "gen_ai.tool.name") or (name if kind == "tool" else None),
            "tool_args": _parse_payload(_attribute(attributes, "spantrace.tool_args")),
            "tool_result": _parse_payload(_attribute(attributes, "spantrace.tool_result")),
            "model_name": _attribute(attributes, "spantrace.model_name", "gen_ai.request.model") or (name if kind == "model" else None),
            "handoff_to": _attribute(attributes, "spantrace.handoff_to"),
            "error_type": _attribute(attributes, "spantrace.error_type"),
            "error_details": error_details,
            "integration": "opentelemetry",
            "framework": str(_attribute(attributes, "spantrace.framework") or self.framework),
            "framework_run_id": str(framework_run_id) if framework_run_id else None,
            "framework_parent_id": parent_span_id,
            "relationship": relationship,
            "relationship_confidence": confidence,
            "metadata": metadata,
        }

        if parent_span_id is None and trace_id not in self._roots_seen:
            self._roots_seen.add(trace_id)
            self._emit({**event, "event_id": f"otel:{trace_id}:start", "event_type": "run_started", "kind": "workflow", "status": "running", "span_id": span_id, "parent_span_id": None, "occurred_at": start, "ended_at": None, "duration_ms": None, "agent_name": name, "output": None})
        if parent_span_id is not None or event_type not in {"run_started", "run_completed", "run"}:
            self._emit(event)
        if parent_span_id is None:
            self._emit({**event, "event_id": f"otel:{trace_id}:complete", "event_type": "run_completed", "kind": "workflow", "status": status, "occurred_at": end, "ended_at": end, "duration_ms": duration_ms, "agent_name": name, "input": None})

        for index, otel_event in enumerate(getattr(span, "events", ()) or ()):
            event_name = str(getattr(otel_event, "name", ""))
            event_attributes = dict(getattr(otel_event, "attributes", {}) or {})
            if event_name == "exception":
                self._emit({**event, "event_id": f"otel:{trace_id}:{span_id}:exception:{index}", "event_type": "exception", "kind": "exception", "status": "failed", "occurred_at": _iso_nanos(getattr(otel_event, "timestamp", None)), "ended_at": None, "duration_ms": None, "error_type": str(event_attributes.get("exception.type") or "Exception"), "error_details": str(event_attributes.get("exception.message") or "")})
            elif event_name in {"spantrace.handoff", "handoff"}:
                target_span_id = event_attributes.get("spantrace.target_span_id")
                self._emit({**event, "event_id": f"otel:{trace_id}:{span_id}:handoff:{index}", "event_type": "handoff", "kind": "handoff", "span_id": f"{span_id}:handoff:{index}", "parent_span_id": span_id, "agent_name": str(event_attributes.get("spantrace.from_agent") or name), "handoff_to": event_attributes.get("spantrace.to_agent"), "relationship": "handoff", "relationship_confidence": "observed" if target_span_id else "unknown", "metadata": {**metadata, "target_span_id": target_span_id}})

    def shutdown(self) -> None:
        self.scope.flush()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        self.scope.flush()
        return True


class OpenTelemetryAdapter:
    name = "opentelemetry"

    def __init__(self, scope: AgentScope, *, framework: str = "opentelemetry") -> None:
        self.scope = scope
        self.framework = framework
        self.exporter = SpanTraceSpanExporter(scope, framework=framework)

    def create_provider(self, *, service_name: str = "spantrace-workflow") -> Any:
        if not OTEL_AVAILABLE:
            raise RuntimeError("OpenTelemetry integration requires opentelemetry-api and opentelemetry-sdk")
        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        # The batch processor keeps export work off the application's span
        # completion path. provider.shutdown() flushes the bounded queue.
        provider.add_span_processor(BatchSpanProcessor(self.exporter, schedule_delay_millis=10))
        return provider

    def diagnostics(self) -> dict[str, Any]:
        return {
            "integration": self.name,
            "framework": self.framework,
            "available": OTEL_AVAILABLE,
            "events_exported": self.exporter.events_exported,
            "last_export_at": self.exporter.last_export_at,
            "capture_payloads": self.scope.capture_payloads,
        }
