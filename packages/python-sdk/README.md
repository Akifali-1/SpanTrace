# SpanTrace Python SDK

The SDK keeps the Task 1 `agentscope` import for compatibility and adds the canonical `spantrace` import. The base client uses the standard library and fails open by default so observability outages do not crash an application. OpenTelemetry support is an optional integration dependency.

```python
from spantrace import SpanTrace

scope = SpanTrace.from_env()
with scope.trace("travel-booking") as trace:
    with trace.span("planner", kind="agent", input={"destination": "Goa"}) as planner:
        planner.set_output({"nights": 2})
    trace.handoff("hotel-search", from_agent="planner")
    with trace.tool("search_hotels", args={"destination": "Goa"}) as search:
        search.set_output({"hotels": [{"name": "Palm Grove", "price_inr": 4200}]})
```

Automatic OpenTelemetry instrumentation is opt-in and uses public SDK APIs:

```python
provider, adapter = scope.instrument_opentelemetry(service_name="my-workflow", framework="my-framework")
tracer = provider.get_tracer("my-app")
with tracer.start_as_current_span("planner", attributes={"spantrace.kind": "agent"}):
    run_planner()
provider.shutdown()
```

For callback-based frameworks, use `CallbackAdapter(scope, framework="your-framework")` from `agentscope.integrations` or `spantrace.integrations`. It exposes explicit lifecycle methods for nodes, models, tools, handoffs, retries, exceptions, and workflow completion.

Environment variables: `SPANTRACE_API_KEY`, `SPANTRACE_API_URL`, `SPANTRACE_PROJECT_ID`, `SPANTRACE_CAPTURE_PAYLOADS`, `SPANTRACE_STRICT`, `SPANTRACE_BATCH_SIZE`, and `SPANTRACE_TIMEOUT`. The equivalent `AGENTSCOPE_` names remain supported.
