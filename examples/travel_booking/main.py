from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../packages/python-sdk")))

from spantrace import SpanTrace

# Keep the Task 1 symbol available for the manual compatibility runner and
# existing downstream tests while the example uses the canonical name.
AgentScope = SpanTrace


@dataclass
class MockBookingAPI:
    """Deterministic local API; it never calls a real booking provider."""

    def search_hotels(self, destination: str, nights: int) -> list[dict[str, Any]]:
        return [
            {"hotel": "Palm Grove Goa", "nightly_price_inr": 4200, "nights": nights, "available": True},
            {"hotel": "Monsoon House", "nightly_price_inr": 4700, "nights": nights, "available": True},
        ]

    def create_reservation(self, hotel: dict[str, Any]) -> dict[str, Any]:
        return {"reservation_id": "MOCK-GOA-0001", "hotel": hotel["hotel"], "created": True}


def run(mode: str, *, api_key: str | None = None, api_url: str | None = None, project_id: str | None = None) -> str:
    scope = AgentScope(
        api_key=api_key or os.getenv("SPANTRACE_API_KEY") or os.getenv("AGENTSCOPE_API_KEY"),
        endpoint=api_url or os.getenv("SPANTRACE_API_URL") or os.getenv("AGENTSCOPE_API_URL", "http://localhost:8070"),
        project_id=project_id or os.getenv("SPANTRACE_PROJECT_ID") or os.getenv("AGENTSCOPE_PROJECT_ID"),
        strict=True,
        capture_payloads=True,
    )
    booking_api = MockBookingAPI()
    request = {"destination": "Goa", "nights": 2, "max_price_inr": 5000, "approval_required": True}
    fixed = mode == "fixed"
    failure = mode == "failure"
    approved = mode == "approved"

    with scope.trace("travel-booking", metadata={"demo": True, "mode": mode, "scenario": request}) as trace:
        with trace.span("planner", kind="agent", input=request) as planner:
            plan = {"destination": "Goa", "nights": 2, "max_price_inr": 5000, "approval_required": True}
            planner.set_output(plan)
        trace.handoff("hotel-search", from_agent="planner", metadata={"reason": "plan_ready"})

        with trace.span("hotel-search", kind="agent", input=plan) as hotel_search:
            with trace.tool("search_hotels", args={"destination": "Goa", "nights": 2}) as search:
                hotels = booking_api.search_hotels("Goa", 2)
                search.set_output(hotels)
            hotel_search.set_output({"candidate_count": len(hotels), "selected": hotels[0]})
        trace.handoff("budget-validator", from_agent="hotel-search")

        with trace.span("budget-validator", kind="agent", input={"hotel": hotels[0], "max_price_inr": 5000}) as budget:
            within_budget = hotels[0]["nightly_price_inr"] <= 5000
            budget.set_output({"within_budget": within_budget, "nightly_price_inr": hotels[0]["nightly_price_inr"]})
        trace.handoff("approval-policy", from_agent="budget-validator")

        approval_state = "approved" if approved else "pending"
        with trace.span("approval-policy", kind="policy", input={"approval_required": True}) as approval:
            approval.set_output({"approval_state": approval_state, "recorded_by": "demo-policy"})

        trace.handoff("booking", from_agent="approval-policy")
        with trace.span("booking", kind="agent", input={"hotel": hotels[0], "approval_state": approval_state}) as booking:
            should_book = approved or failure
            if should_book:
                # `failure` is deliberately defective demo code. It bypasses
                # the pending approval state, but only invokes the mock API.
                with trace.tool("create_reservation", args={"hotel": hotels[0], "approval_state": approval_state, "approval_required": True}) as reservation:
                    result = booking_api.create_reservation(hotels[0])
                    reservation.set_output(result)
                booking.set_output({"status": "booked", "reservation_id": result["reservation_id"]})
            else:
                booking.set_output({"status": "waiting_for_approval", "reservation_created": False})
        trace.handoff("final-response", from_agent="booking")

        with trace.span("final-response", kind="agent", input={"mode": mode}) as final:
            final.set_output({"message": "Reservation created." if (approved or failure) else "Ready when approval is granted.", "mode": mode, "fixed": fixed})

    print(f"mode={mode} trace_id={trace.trace_id}")
    return trace.trace_id


def run_otel(mode: str, *, api_key: str | None = None, api_url: str | None = None, project_id: str | None = None) -> str:
    """Run the same workflow through public OpenTelemetry span APIs.

    No SpanTrace span or tool wrapper is used here. The application emits
    supported OpenTelemetry spans and SpanTrace's exporter normalizes the
    completed execution into its framework-independent event schema.
    """
    from opentelemetry.trace import Status, StatusCode
    from spantrace import SpanTrace

    scope = SpanTrace(
        api_key=api_key or os.getenv("SPANTRACE_API_KEY") or os.getenv("AGENTSCOPE_API_KEY"),
        endpoint=api_url or os.getenv("SPANTRACE_API_URL") or os.getenv("AGENTSCOPE_API_URL", "http://localhost:8070"),
        project_id=project_id or os.getenv("SPANTRACE_PROJECT_ID") or os.getenv("AGENTSCOPE_PROJECT_ID"),
        strict=True,
        capture_payloads=True,
    )
    provider, adapter = scope.instrument_opentelemetry(service_name="spantrace-travel-booking", framework="deterministic-booking")
    tracer = provider.get_tracer("spantrace.travel_booking")
    booking_api = MockBookingAPI()
    request = {"destination": "Goa", "nights": 2, "max_price_inr": 5000, "approval_required": True}
    failure = mode == "failure"
    approved = mode == "approved"

    def attrs(kind: str, name: str, **values: Any) -> dict[str, Any]:
        result: dict[str, Any] = {
            "spantrace.kind": kind,
            "spantrace.agent_name": name,
            "spantrace.framework": "deterministic-booking",
            "spantrace.framework_run_id": "booking-demo",
        }
        result.update({key: json.dumps(value, default=str) if key in {"spantrace.input", "spantrace.output", "spantrace.tool_args", "spantrace.tool_result"} else value for key, value in values.items()})
        return result

    with tracer.start_as_current_span("travel-booking", attributes=attrs("workflow", "travel-booking", **{"spantrace.event_type": "run"})) as root:
        root_context = root.get_span_context()
        trace_id = f"{root_context.trace_id:032x}"
        with tracer.start_as_current_span("planner", attributes=attrs("agent", "planner", **{"spantrace.input": request})) as planner:
            with tracer.start_as_current_span("deterministic-model", attributes=attrs("model", "deterministic-model", **{"spantrace.event_type": "model_call", "spantrace.model_name": "deterministic-model", "spantrace.input": request, "spantrace.output": {"plan": "book within budget"}})):
                plan = {"destination": "Goa", "nights": 2, "max_price_inr": 5000, "approval_required": True}
            planner.set_attribute("spantrace.output", json.dumps(plan))
            planner.add_event("spantrace.handoff", {"spantrace.to_agent": "hotel-search", "spantrace.from_agent": "planner"})

        with tracer.start_as_current_span("hotel-search", attributes=attrs("agent", "hotel-search", **{"spantrace.input": plan})) as hotel_search:
            with tracer.start_as_current_span("search_hotels", attributes=attrs("tool", "search_hotels", **{"spantrace.event_type": "tool_call", "spantrace.tool_name": "search_hotels", "spantrace.tool_args": {"destination": "Goa", "nights": 2}})) as search:
                hotels = booking_api.search_hotels("Goa", 2)
                search.set_attribute("spantrace.tool_result", json.dumps(hotels))
            hotel_search.set_attribute("spantrace.output", json.dumps({"candidate_count": len(hotels), "selected": hotels[0]}))
            hotel_search.add_event("spantrace.handoff", {"spantrace.to_agent": "budget-validator", "spantrace.from_agent": "hotel-search"})

        with tracer.start_as_current_span("budget-validator", attributes=attrs("agent", "budget-validator", **{"spantrace.input": {"hotel": hotels[0], "max_price_inr": 5000}})) as budget:
            within_budget = hotels[0]["nightly_price_inr"] <= 5000
            budget.set_attribute("spantrace.output", json.dumps({"within_budget": within_budget, "nightly_price_inr": hotels[0]["nightly_price_inr"]}))
            budget.add_event("spantrace.handoff", {"spantrace.to_agent": "approval-policy", "spantrace.from_agent": "budget-validator"})

        approval_state = "approved" if approved else "pending"
        with tracer.start_as_current_span("approval-policy", attributes=attrs("policy", "approval-policy", **{"spantrace.event_type": "agent_span", "spantrace.input": {"approval_required": True}, "spantrace.output": {"approval_state": approval_state, "recorded_by": "demo-policy"}})) as approval:
            approval.add_event("spantrace.handoff", {"spantrace.to_agent": "booking", "spantrace.from_agent": "approval-policy"})

        with tracer.start_as_current_span("booking", attributes=attrs("agent", "booking", **{"spantrace.input": {"hotel": hotels[0], "approval_state": approval_state}})) as booking:
            should_book = approved or failure
            if should_book:
                with tracer.start_as_current_span("create_reservation", attributes=attrs("tool", "create_reservation", **{"spantrace.event_type": "tool_call", "spantrace.tool_name": "create_reservation", "spantrace.tool_args": {"hotel": hotels[0], "approval_state": approval_state, "approval_required": True}})) as reservation:
                    result = booking_api.create_reservation(hotels[0])
                    reservation.set_attribute("spantrace.tool_result", json.dumps(result))
                booking.set_attribute("spantrace.output", json.dumps({"status": "booked", "reservation_id": result["reservation_id"]}))
                if failure:
                    booking.set_status(Status(StatusCode.ERROR, "approval policy was bypassed"))
                    booking.add_event("exception", {"exception.type": "ApprovalPolicyViolation", "exception.message": "booking invoked while approval was pending"})
            else:
                booking.set_attribute("spantrace.output", json.dumps({"status": "waiting_for_approval", "reservation_created": False}))
            booking.add_event("spantrace.handoff", {"spantrace.to_agent": "final-response", "spantrace.from_agent": "booking"})

        with tracer.start_as_current_span("final-response", attributes=attrs("agent", "final-response", **{"spantrace.input": {"mode": mode}, "spantrace.output": {"message": "Reservation created." if (approved or failure) else "Ready when approval is granted.", "mode": mode}})):
            pass

    provider.shutdown()
    adapter.exporter.shutdown()
    print(f"mode={mode} integration=opentelemetry trace_id={trace_id}")
    return trace_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the deterministic SpanTrace travel-booking demo")
    parser.add_argument("--mode", choices=["normal", "approved", "failure", "fixed"], default="normal")
    parser.add_argument("--integration", choices=["opentelemetry", "manual"], default="opentelemetry")
    parser.add_argument("--api-key")
    parser.add_argument("--api-url")
    parser.add_argument("--project-id")
    args = parser.parse_args()
    runner = run_otel if args.integration == "opentelemetry" else run
    runner(args.mode, api_key=args.api_key, api_url=args.api_url, project_id=args.project_id)
