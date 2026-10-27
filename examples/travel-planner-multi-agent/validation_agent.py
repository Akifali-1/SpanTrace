from __future__ import annotations

from typing import Any

from models import TripRequest
from telemetry import handoff


def recompute_itinerary_total_tool(itinerary: dict[str, Any]) -> int:
    breakdown = itinerary["cost_breakdown_cents"]
    return sum(int(value) for value in breakdown.values())


def validation_agent(request: TripRequest, itinerary: dict[str, Any], trace, span) -> dict[str, Any]:
    with span:
        with trace.tool("recompute_itinerary_total", args={"breakdown": itinerary["cost_breakdown_cents"]}) as tool:
            actual_total_cents = recompute_itinerary_total_tool(itinerary)
            tool.set_output({"actual_total_cents": actual_total_cents})
        required_fields_present = all(itinerary.get(field) for field in ("destination", "transport", "accommodation", "activities"))
        budget_compliant = actual_total_cents <= request.budget_cents
        reported_total_consistent = actual_total_cents == itinerary["reported_total_cents"]
        result = {
            "agent": "validation-agent",
            "valid": budget_compliant and required_fields_present,
            "budget_compliant": budget_compliant,
            "required_fields_present": required_fields_present,
            "reported_total_consistent": reported_total_consistent,
            "actual_total_cents": actual_total_cents,
            "reported_total_cents": itinerary["reported_total_cents"],
            "budget_cents": request.budget_cents,
        }
        span.set_output(result)
        return result
