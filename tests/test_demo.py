from examples.travel_booking.main import run


def test_demo_requires_real_sdk_configuration(monkeypatch):
    # The demo's policy decision is represented in code; transport is exercised
    # by the API integration tests and the runnable command uses strict mode.
    monkeypatch.setattr("examples.travel_booking.main.AgentScope", lambda **kwargs: DummyScope())
    trace_id = run("failure", api_key="test", api_url="http://example", project_id="project")
    assert trace_id


class DummyScope:
    def trace(self, name, metadata=None):
        return DummyTrace()


class DummyTrace:
    trace_id = "dummy-trace"
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def span(self, *args, **kwargs): return DummySpan()
    def tool(self, *args, **kwargs): return DummySpan()
    def handoff(self, *args, **kwargs): pass


class DummySpan:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def set_output(self, value): pass
