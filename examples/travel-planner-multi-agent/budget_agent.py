from __future__ import annotations

from typing import Any

from models import TripRequest
from telemetry import handoff


def calculate_budget(
    request: TripRequest,
    transport: dict[str, Any],
    accommodation: dict[str, Any],
    activities: dict[str, Any],
    *,
    adjustment: bool = False,
) -> dict[str, Any]:
    # INTENTIONAL DEMO BUG: for the named bug fixture, every price is
    # contractually in cents but the transport amount is incorrectly converted
    # to currency units. The ordinary success fixture uses the same contract
    # and follows the correct path so the demonstrations remain distinct.
    transport_cost_cents = transport["price_cents"] // (100 if request.scenario == "bug" else 1)
    accommodation_cost_cents = accommodation["total_cents"]
    activities_cost_cents = activities["total_cents"]
    reported_total_cents = transport_cost_cents + accommodation_cost_cents + activities_cost_cents
    return {
        "agent": "budget-agent",
        "transport_source_price_cents": transport["price_cents"],
        "transport_added_cents": transport_cost_cents,
        "accommodation_cents": accommodation_cost_cents,
        "activities_cents": activities_cost_cents,
        "reported_total_cents": reported_total_cents,
        "budget_cents": request.budget_cents,
        "decision": "within_budget" if reported_total_cents <= request.budget_cents else "over_budget",
        "adjustment": adjustment,
    }


def budget_agent(
    request: TripRequest,
    transport: dict[str, Any],
    accommodation: dict[str, Any],
    activities: dict[str, Any],
    trace,
    span,
    *,
    adjustment: bool = False,
    next_span_id: str | None = None,
    next_name: str = "itinerary-agent",
    over_budget_span_id: str | None = None,
    over_budget_name: str = "adjustment-pass",
) -> dict[str, Any]:
    with span:
        with trace.tool("aggregate_budget", args={"price_unit": "cents", "adjustment": adjustment}) as tool:
            result = calculate_budget(request, transport, accommodation, activities, adjustment=adjustment)
            tool.set_output(result)
        span.set_output(result)
        target_name = over_budget_name if result["decision"] == "over_budget" and over_budget_span_id else next_name
        target_id = over_budget_span_id if target_name == over_budget_name else next_span_id
        handoff(trace, span, target_name, target_span_id=target_id, metadata={"decision": result["decision"], "attempt": 2 if adjustment else 1})
        return result
