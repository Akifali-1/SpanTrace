from __future__ import annotations

from typing import Any

from fixtures import ACCOMMODATION_OPTIONS
from models import TripRequest
from telemetry import handoff


def lookup_accommodation_tool(request: TripRequest, *, adjustment: bool = False) -> list[dict[str, Any]]:
    options = list(ACCOMMODATION_OPTIONS.get(request.destination, ()))
    return [options[1]] if adjustment and len(options) > 1 else options


def accommodation_agent(
    request: TripRequest,
    trace,
    span,
    *,
    adjustment: bool = False,
    next_span_id: str | None = None,
) -> dict[str, Any]:
    with span:
        with trace.tool("lookup_accommodation_options", args={"destination": request.destination, "adjustment": adjustment}) as tool:
            options = lookup_accommodation_tool(request, adjustment=adjustment)
            tool.set_output(options)
        if not options:
            raise ValueError("no accommodation options available")
        selected = options[0]
        total_cents = selected["nightly_price_cents"] * request.nights
        result = {
            "agent": "accommodation-agent",
            "selected": selected,
            "nights": request.nights,
            "nightly_price_cents": selected["nightly_price_cents"],
            "total_cents": total_cents,
            "adjustment": adjustment,
        }
        span.set_output(result)
        handoff(trace, span, "budget-agent", target_span_id=next_span_id, metadata={"attempt": 2 if adjustment else 1})
        return result
