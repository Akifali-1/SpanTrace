from __future__ import annotations

from typing import Any

from fixtures import ACTIVITY_OPTIONS
from models import TripRequest
from telemetry import handoff


def lookup_activities_tool(request: TripRequest, *, adjustment: bool = False) -> list[dict[str, Any]]:
    options = list(ACTIVITY_OPTIONS.get(request.destination, ()))
    if adjustment:
        return [item for item in options if item["category"] == "outdoors"]
    return [item for item in options if item["category"] in request.activity_preferences]


def activities_agent(
    request: TripRequest,
    trace,
    span,
    *,
    adjustment: bool = False,
    next_span_id: str | None = None,
) -> dict[str, Any]:
    with span:
        with trace.tool("lookup_matching_activities", args={"preferences": request.activity_preferences, "adjustment": adjustment}) as tool:
            activities = lookup_activities_tool(request, adjustment=adjustment)
            tool.set_output(activities)
        if not activities:
            raise ValueError("no matching activities available")
        total_cents = sum(item["price_cents"] for item in activities)
        result = {"agent": "activities-agent", "activities": activities, "total_cents": total_cents, "adjustment": adjustment}
        span.set_output(result)
        handoff(trace, span, "budget-agent", target_span_id=next_span_id, metadata={"attempt": 2 if adjustment else 1})
        return result
