from collections.abc import Iterable
from typing import Any


def _approval_state(event: Any) -> str | None:
    output = getattr(event, "output_json", None) or {}
    metadata = getattr(event, "metadata_json", None) or {}
    if isinstance(output, dict) and output.get("approval_state"):
        return str(output["approval_state"]).lower()
    if isinstance(metadata, dict) and metadata.get("approval_state"):
        return str(metadata["approval_state"]).lower()
    return None


def evaluate_incidents(events: Iterable[Any]) -> list[dict[str, Any]]:
    """Evaluate deterministic policy rules from persisted evidence only.

    The detector intentionally reports uncertainty when it cannot establish the
    required approval state. It never infers a policy violation from a missing
    event alone.
    """
    ordered = sorted(events, key=lambda item: getattr(item, "occurred_at"))
    incidents: list[dict[str, Any]] = []
    approval_state: str | None = None
    approval_event_id: str | None = None

    for event in ordered:
        state = _approval_state(event)
        if state is not None and (event.event_type in {"approval", "policy", "workflow"} or event.kind == "policy" or event.event_type.startswith("approval")):
            approval_state = state
            approval_event_id = event.event_id

        if event.event_type != "tool_call" or event.tool_name != "create_reservation":
            continue

        args = event.tool_args if isinstance(event.tool_args, dict) else {}
        result = event.tool_result if isinstance(event.tool_result, dict) else {}
        reservation_created = bool(result.get("reservation_id") or result.get("created"))
        if not reservation_created:
            continue

        if approval_state in {"pending", "denied"}:
            incidents.append(
                {
                    "rule": "reservation_requires_approval",
                    "severity": "high",
                    "title": "Reservation created before approval",
                    "summary": f"create_reservation ran while approval was {approval_state}.",
                    "violating_event_id": event.event_id,
                    "responsible_span_id": event.span_id,
                    "responsible_parent_span_id": event.parent_span_id,
                    "evidence": [
                        {"event_id": approval_event_id, "fact": f"Recorded approval state was {approval_state}."},
                        {"event_id": event.event_id, "fact": "Recorded create_reservation tool result contained a reservation."},
                    ],
                    "observed_facts": [
                        f"approval_state={approval_state}",
                        f"reservation_created={reservation_created}",
                    ],
                    "inference": "The tool invocation violated the configured approval invariant.",
                    "arguments": args,
                }
            )
        elif approval_state is None:
            incidents.append(
                {
                    "rule": "reservation_requires_approval",
                    "severity": "unknown",
                    "title": "Approval evidence is missing",
                    "summary": "A reservation was created, but this trace does not record an approval state.",
                    "violating_event_id": event.event_id,
                    "responsible_span_id": event.span_id,
                    "responsible_parent_span_id": event.parent_span_id,
                    "evidence": [{"event_id": event.event_id, "fact": "Recorded create_reservation tool result contained a reservation."}],
                    "observed_facts": ["reservation_created=True", "approval_state=missing"],
                    "inference": "The trace is insufficient to determine whether approval was required or granted.",
                    "arguments": args,
                }
            )

    return incidents
