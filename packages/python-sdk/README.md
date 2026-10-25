# AgentScope Python SDK

The SDK is intentionally dependency-free. It sends framework-independent events to the AgentScope API using the standard library and fails open by default so observability outages do not crash an application.

```python
from agentscope import AgentScope

scope = AgentScope.from_env()
with scope.trace("travel-booking") as trace:
    with trace.span("planner", kind="agent", input={"destination": "Goa"}) as planner:
        planner.set_output({"nights": 2})
    trace.handoff("hotel-search", from_agent="planner")
    with trace.tool("search_hotels", args={"destination": "Goa"}) as search:
        search.set_output({"hotels": [{"name": "Palm Grove", "price_inr": 4200}]})
```

Environment variables: `AGENTSCOPE_API_KEY`, `AGENTSCOPE_API_URL`, `AGENTSCOPE_PROJECT_ID`, `AGENTSCOPE_CAPTURE_PAYLOADS`, `AGENTSCOPE_STRICT`, `AGENTSCOPE_BATCH_SIZE`, and `AGENTSCOPE_TIMEOUT`.
