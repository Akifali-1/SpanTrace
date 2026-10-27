from __future__ import annotations

from typing import Any


def authorize_payment(customer_id: str, amount_cents: int) -> dict[str, Any]:
    """Deterministic local payment authorization; no provider is contacted."""

    if amount_cents <= 0:
        return {"authorized": False, "reason": "amount must be positive"}
    return {"authorized": True, "authorization_id": f"MOCK-AUTH-{customer_id}-001", "amount_cents": amount_cents}


def authorize_payment_tool(customer_id: str, amount_cents: int) -> dict[str, Any]:
    return authorize_payment(customer_id, amount_cents)
