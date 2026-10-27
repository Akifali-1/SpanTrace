from __future__ import annotations

from typing import Any

from fixtures import TRANSPORT_OPTIONS
from models import TripRequest
from telemetry import handoff


def lookup_transport_tool(request: TripRequest, *, adjustment: bool = False) -> list[dict[str, Any]]:
    options = list(TRANSPORT_OPTIONS.get(request.destination, ()))
    return options[1:] if adjustment else options


def transport_agent(
    request: TripRequest,
    trace,
    span,
    *,
    adjustment: bool = False,
    next_span_id: str | None = None,
) -> dict[str, Any]:
    with span:
        with trace.tool("lookup_transport_options", args={"destination": request.destination, "adjustment": adjustment}) as tool:
            options = lookup_transport_tool(request, adjustment=adjustment)
            tool.set_output(options)
        if not options:
            raise ValueError("no transport options available")
        selected = options[0]
        result = {"agent": "transport-agent", "selected": selected, "price_cents": selected["price_cents"], "adjustment": adjustment}
        span.set_output(result)
        handoff(trace, span, "budget-agent", target_span_id=next_span_id, metadata={"attempt": 2 if adjustment else 1})
        return result
