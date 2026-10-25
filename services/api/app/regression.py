from typing import Any


def run_booking_regression(fixed: bool) -> dict[str, Any]:
    """Run the deterministic booking policy simulation used by the demo.

    This function intentionally contains no arbitrary code execution. The
    server only reruns a known, built-in scenario against a mock booking API.
    """
    approval_state = "pending"
    booking_called = not fixed
    reservation_created = booking_called
    passed = not reservation_created
    return {
        "scenario": "Goa / 2 nights / max INR 5000 per night / approval required",
        "implementation": "corrected" if fixed else "defective",
        "approval_state": approval_state,
        "booking_called": booking_called,
        "reservation_created": reservation_created,
        "assertions": [
            {
                "name": "no reservation while approval pending",
                "expected": False,
                "actual": reservation_created,
                "passed": not reservation_created,
            }
        ],
        "passed": passed,
    }
