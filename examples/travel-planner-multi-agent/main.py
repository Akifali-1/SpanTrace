from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

SDK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../packages/python-sdk"))
if SDK_ROOT not in sys.path:
    sys.path.insert(0, SDK_ROOT)

try:
    from accommodation_agent import accommodation_agent
    from activities_agent import activities_agent
    from budget_agent import budget_agent
    from fixtures import fixture_for
    from itinerary_agent import itinerary_agent
    from models import TripRequest
    from telemetry import new_scope, workflow_trace
    from transport_agent import transport_agent
    from validation_agent import validation_agent
    from workflow import coordinate_trip
except ModuleNotFoundError:
    sys.path.insert(0, os.path.dirname(__file__))
    from accommodation_agent import accommodation_agent
    from activities_agent import activities_agent
    from budget_agent import budget_agent
    from fixtures import fixture_for
    from itinerary_agent import itinerary_agent
    from models import TripRequest
    from telemetry import new_scope, workflow_trace
    from transport_agent import transport_agent
    from validation_agent import validation_agent
    from workflow import coordinate_trip


def run_trip(request: TripRequest, trace) -> dict[str, Any]:
    coordinator_span = trace.span("trip-coordinator", kind="agent", input=request.__dict__)
    transport_span = trace.span("transport-agent", kind="agent", input={"destination": request.destination})
    accommodation_span = trace.span("accommodation-agent", kind="agent", input={"destination": request.destination})
    activities_span = trace.span("activities-agent", kind="agent", input={"destination": request.destination})
    budget_span = trace.span("budget-agent", kind="agent", input={"budget_cents": request.budget_cents})
    adjustment_span = trace.span("adjustment-pass", kind="agent", input={"budget_cents": request.budget_cents}, metadata={"attempt": 2})
    adjustment_transport_span = trace.span("transport-agent", kind="agent", input={"destination": request.destination}, metadata={"attempt": 2})
    adjustment_accommodation_span = trace.span("accommodation-agent", kind="agent", input={"destination": request.destination}, metadata={"attempt": 2})
    adjustment_activities_span = trace.span("activities-agent", kind="agent", input={"destination": request.destination}, metadata={"attempt": 2})
    retry_budget_span = trace.span("budget-agent", kind="agent", input={"budget_cents": request.budget_cents}, metadata={"attempt": 2})
    itinerary_span = trace.span("itinerary-agent", kind="agent", input={"destination": request.destination})
    validation_span = trace.span("validation-agent", kind="agent", input={"destination": request.destination})
    return coordinate_trip(
        request,
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
    )


def main(inputs: dict[str, Any]) -> dict[str, Any]:
    """Task 4 entry point; all inputs are deterministic JSON fixture selectors."""

    inputs = inputs or {}
    scenario = str(inputs.get("scenario", "success"))
    fixture = fixture_for(scenario)
    request = TripRequest.from_inputs(fixture)
    scope = new_scope()
    metadata = {"demo": "travel-planner-multi-agent", "scenario": scenario}
    with workflow_trace(scope, "travel-planner-multi-agent", metadata) as trace:
        return run_trip(request, trace)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the deterministic travel-planner SpanTrace demo")
    parser.add_argument("--scenario", choices=["success", "bug", "adjustment"], default="success")
    args = parser.parse_args()
    print(json.dumps(main({"scenario": args.scenario}), default=str, sort_keys=True))
