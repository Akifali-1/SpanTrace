import json
import urllib.error

import pytest

from agentscope import AgentScope
from agentscope.client import default_redactor


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
