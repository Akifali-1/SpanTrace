import json
import asyncio
import urllib.error

import pytest

from agentscope import AgentScope
from agentscope.client import default_redactor
from agentscope.integrations import CallbackAdapter


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_nested_spans_and_redaction(monkeypatch):
    sent = []

    def fake_urlopen(request, timeout):
        sent.append(json.loads(request.data))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    scope = AgentScope("ask_test", batch_size=100)
    with scope.trace("demo") as trace:
        with trace.span("planner", input={"token": "secret", "destination": "Goa"}) as planner:
            planner.set_output({"ok": True})
            with trace.tool("search", args={"api_key": "hidden"}) as tool:
                tool.set_output({"hotels": 1})
        trace.handoff("booking", from_agent="planner")
    events = sent[0]["events"]
    planner_event = next(item for item in events if item["agent_name"] == "planner")
    tool_event = next(item for item in events if item["event_type"] == "tool_call")
    assert planner_event["input"]["token"] == "[REDACTED]"
    assert tool_event["tool_args"]["api_key"] == "[REDACTED]"
    assert tool_event["parent_span_id"] == planner_event["span_id"]
    assert any(item["event_type"] == "handoff" for item in events)


def test_capture_disabled_and_network_failure_is_non_fatal(monkeypatch):
    scope = AgentScope("ask_test", capture_payloads=False)
    with scope.trace("demo") as trace:
        with trace.span("agent", input={"secret": "value"}):
            pass
    assert all(event["input"] in (None, {"captured": False}) for event in scope._buffer)

    def fail(*args, **kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    scope.flush()
    assert scope.last_error is not None


def test_strict_network_failure_raises(monkeypatch):
    def fail(*args, **kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    scope = AgentScope("ask_test", strict=True)
    with pytest.raises(RuntimeError):
        with scope.trace("demo"):
            pass


def test_redactor_handles_nested_values():
    value = default_redactor({"authorization": "Bearer x", "nested": [{"password": "p"}], "safe": 1})
    assert value == {"authorization": "[REDACTED]", "nested": [{"password": "[REDACTED]"}], "safe": 1}


def test_async_context_propagates_parallel_parent_ids(monkeypatch):
    sent = []

    def fake_urlopen(request, timeout):
        sent.append(json.loads(request.data))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    async def run_parallel():
        scope = AgentScope("ask_test", batch_size=100)
        async with scope.trace("async-workflow") as trace:
            async with trace.span("parent") as parent:
                async def child(name):
                    async with trace.span(name):
                        await asyncio.sleep(0)

                await asyncio.gather(child("left"), child("right"))
                parent.set_output({"branches": 2})

    asyncio.run(run_parallel())
    events = sent[0]["events"]
    parent = next(item for item in events if item["agent_name"] == "parent")
    children = [item for item in events if item["agent_name"] in {"left", "right"}]
    assert len(children) == 2
    assert all(item["parent_span_id"] == parent["span_id"] for item in children)


def test_callback_adapter_preserves_framework_relationships(monkeypatch):
    sent = []

    def fake_urlopen(request, timeout):
        sent.append(json.loads(request.data))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    scope = AgentScope("ask_test", batch_size=100)
    adapter = CallbackAdapter(scope, framework="deterministic-test")
    adapter.workflow_started(trace_id="callback-trace", run_name="workflow", run_id="root")
    adapter.node_started(trace_id="callback-trace", node_id="planner", name="planner", parent_id="root", run_id="root")
    adapter.tool_completed(trace_id="callback-trace", span_id="search", tool_name="search", parent_id="planner", args={"api_key": "secret"}, result={"ok": True}, run_id="root")
    adapter.handoff(trace_id="callback-trace", source_span_id="planner", from_agent="planner", to_agent="booking", run_id="root")
    adapter.workflow_completed(trace_id="callback-trace", run_name="workflow", run_id="root")
    scope.flush()

    events = sent[0]["events"]
    tool = next(item for item in events if item["event_type"] == "tool_call")
    handoff = next(item for item in events if item["event_type"] == "handoff")
    assert tool["framework"] == "deterministic-test"
    assert tool["parent_span_id"] == "planner"
    assert tool["tool_args"]["api_key"] == "[REDACTED]"
    assert handoff["relationship_confidence"] == "unknown"


def test_opentelemetry_adapter_exports_lifecycle_model_tool_and_handoff(monkeypatch):
    sent = []

    def fake_urlopen(request, timeout):
        sent.append(json.loads(request.data))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    from opentelemetry.trace import Status, StatusCode

    scope = AgentScope("ask_test", batch_size=100)
    provider, _ = scope.instrument_opentelemetry(service_name="test-service", framework="deterministic-test")
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("workflow", attributes={"spantrace.kind": "workflow", "spantrace.event_type": "run"}) as root:
        with tracer.start_as_current_span("planner", attributes={"spantrace.kind": "agent", "spantrace.input": json.dumps({"token": "secret"})}) as planner:
            with tracer.start_as_current_span("model", attributes={"spantrace.kind": "model", "spantrace.event_type": "model_call", "spantrace.model_name": "mock-model", "spantrace.output": json.dumps({"ok": True})}):
                pass
            planner.add_event("spantrace.handoff", {"spantrace.to_agent": "booking"})
        with tracer.start_as_current_span("create_reservation", attributes={"spantrace.kind": "tool", "spantrace.event_type": "tool_call", "spantrace.tool_name": "create_reservation", "spantrace.tool_result": json.dumps({"reservation_id": "mock"})}):
            pass
        root.set_status(Status(StatusCode.OK))
    provider.shutdown()

    events = sent[0]["events"]
    assert {item["event_type"] for item in events} >= {"run_started", "run_completed", "agent_span", "model_call", "tool_call", "handoff"}
    planner = next(item for item in events if item["agent_name"] == "planner")
    model = next(item for item in events if item["event_type"] == "model_call")
    assert model["parent_span_id"] == planner["span_id"]
    assert next(item for item in events if item["event_type"] == "handoff")["relationship_confidence"] == "unknown"
