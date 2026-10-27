from __future__ import annotations

from typing import Any

from models import TripRequest
from telemetry import handoff


def itinerary_agent(
    request: TripRequest,
    transport: dict[str, Any],
    accommodation: dict[str, Any],
    activities: dict[str, Any],
    budget: dict[str, Any],
    trace,
    span,
    *,
    next_span_id: str | None = None,
) -> dict[str, Any]:
    with span:
        breakdown = {
            "transport_cents": transport["price_cents"],
            "accommodation_cents": accommodation["total_cents"],
            "activities_cents": activities["total_cents"],
        }
        result = {
            "destination": request.destination,
            "dates": {"start": request.start_date.isoformat(), "end": request.end_date.isoformat()},
            "travelers": request.travelers,
            "transport": transport["selected"],
            "accommodation": accommodation["selected"],
            "activities": activities["activities"],
            "cost_breakdown_cents": breakdown,
            "reported_total_cents": budget["reported_total_cents"],
            "budget_cents": request.budget_cents,
            "budget_decision": budget["decision"],
        }
        span.set_output(result)
        handoff(trace, span, "validation-agent", target_span_id=next_span_id, metadata={"reason": "itinerary_assembled"})
        return result
