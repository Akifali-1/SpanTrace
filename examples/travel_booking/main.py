from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../packages/python-sdk")))

from agentscope import AgentScope


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
        api_key=api_key or os.getenv("AGENTSCOPE_API_KEY"),
        endpoint=api_url or os.getenv("AGENTSCOPE_API_URL", "http://localhost:8070"),
        project_id=project_id or os.getenv("AGENTSCOPE_PROJECT_ID"),
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the deterministic AgentScope travel-booking demo")
    parser.add_argument("--mode", choices=["normal", "approved", "failure", "fixed"], default="normal")
    parser.add_argument("--api-key")
    parser.add_argument("--api-url")
    parser.add_argument("--project-id")
    args = parser.parse_args()
    run(args.mode, api_key=args.api_key, api_url=args.api_url, project_id=args.project_id)
