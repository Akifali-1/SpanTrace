from __future__ import annotations

from typing import Any


def reserve_inventory(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic local reservation; it only returns a fixture response."""

    return {
        "reserved": True,
        "reservation_id": "MOCK-RESERVATION-0001",
        "items": [{"sku": item["sku"], "quantity": item["quantity"]} for item in items],
    }


def reserve_inventory_tool(items: list[dict[str, Any]]) -> dict[str, Any]:
    return reserve_inventory(items)


def confirm_order(order_id: str, payment: dict[str, Any], reservation: dict[str, Any]) -> dict[str, Any]:
    if not payment.get("authorized") or not reservation.get("reserved"):
        raise RuntimeError("order cannot be confirmed before payment and inventory succeed")
    return {"confirmed": True, "order_id": order_id, "confirmation_id": "MOCK-CONFIRM-0001"}


def confirm_order_tool(order_id: str, payment: dict[str, Any], reservation: dict[str, Any]) -> dict[str, Any]:
    return confirm_order(order_id, payment, reservation)
