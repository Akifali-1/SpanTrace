from __future__ import annotations

from typing import Any

from accommodation_agent import accommodation_agent
from activities_agent import activities_agent
from budget_agent import budget_agent
from itinerary_agent import itinerary_agent
from models import TripRequest
from telemetry import handoff
from transport_agent import transport_agent
from validation_agent import validation_agent


class PlanningValidationError(AssertionError):
    """Raised when independent itinerary validation rejects the plan."""


def adjustment_pass(
    request: TripRequest,
    trace,
    adjustment_span,
    adjustment_transport_span,
    adjustment_accommodation_span,
    adjustment_activities_span,
    retry_budget_span,
    itinerary_span,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    with adjustment_span:
        handoff(trace, adjustment_span, "transport-agent", target_span_id=adjustment_transport_span.span_id, metadata={"adjustment": True})
        transport = transport_agent(request, trace, adjustment_transport_span, adjustment=True, next_span_id=retry_budget_span.span_id)
        handoff(trace, adjustment_span, "accommodation-agent", target_span_id=adjustment_accommodation_span.span_id, metadata={"adjustment": True})
        accommodation = accommodation_agent(request, trace, adjustment_accommodation_span, adjustment=True, next_span_id=retry_budget_span.span_id)
        handoff(trace, adjustment_span, "activities-agent", target_span_id=adjustment_activities_span.span_id, metadata={"adjustment": True})
        activities = activities_agent(request, trace, adjustment_activities_span, adjustment=True, next_span_id=retry_budget_span.span_id)
    return transport, accommodation, activities, budget_agent(
        request,
        transport,
        accommodation,
        activities,
        trace,
        retry_budget_span,
        adjustment=True,
        next_span_id=itinerary_span.span_id,
        next_name="itinerary-agent",
    )


def coordinate_trip(
    request: TripRequest,
    trace,
    coordinator_span,
    transport_span,
    accommodation_span,
    activities_span,
    budget_span,
    adjustment_span,
    adjustment_transport_span,
    adjustment_accommodation_span,
    adjustment_activities_span,
    retry_budget_span,
    itinerary_span,
    validation_span,
) -> dict[str, Any]:
    """Execute the coordinator's real sequential branches and convergence."""

    with coordinator_span:
        handoff(trace, coordinator_span, "transport-agent", target_span_id=transport_span.span_id, metadata={"branch": "transport"})
        transport = transport_agent(request, trace, transport_span, next_span_id=budget_span.span_id)
        handoff(trace, coordinator_span, "accommodation-agent", target_span_id=accommodation_span.span_id, metadata={"branch": "accommodation"})
        accommodation = accommodation_agent(request, trace, accommodation_span, next_span_id=budget_span.span_id)
        handoff(trace, coordinator_span, "activities-agent", target_span_id=activities_span.span_id, metadata={"branch": "activities"})
        activities = activities_agent(request, trace, activities_span, next_span_id=budget_span.span_id)

        budget = budget_agent(
            request,
            transport,
            accommodation,
            activities,
            trace,
            budget_span,
            next_span_id=itinerary_span.span_id,
            next_name="itinerary-agent",
            over_budget_span_id=adjustment_span.span_id,
            over_budget_name="adjustment-pass",
        )
        if budget["decision"] == "over_budget":
            transport, accommodation, activities, budget = adjustment_pass(
                request,
                trace,
                adjustment_span,
                adjustment_transport_span,
                adjustment_accommodation_span,
                adjustment_activities_span,
                retry_budget_span,
                itinerary_span,
            )

        final_budget_span = retry_budget_span if budget_span and budget["adjustment"] else budget_span
        handoff(trace, final_budget_span, "itinerary-agent", target_span_id=itinerary_span.span_id, metadata={"decision": budget["decision"]})
        itinerary = itinerary_agent(request, transport, accommodation, activities, budget, trace, itinerary_span, next_span_id=validation_span.span_id)
        validation = validation_agent(request, itinerary, trace, validation_span)
        result = {"itinerary": itinerary, "budget": budget, "validation": validation}
        if not validation["valid"]:
            raise PlanningValidationError(
                f"itinerary validation failed: actual={validation['actual_total_cents']} budget={request.budget_cents}"
            )
        return result
