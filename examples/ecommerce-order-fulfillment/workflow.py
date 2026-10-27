from __future__ import annotations

from typing import Any

from catalog import lookup_inventory_tool, lookup_products_tool, validate_order_tool
from fulfillment import confirm_order_tool, reserve_inventory_tool
from payments import authorize_payment_tool
from pricing import apply_discount_tool, calculate_subtotal_tool
from telemetry import handoff


class OrderInvariantError(AssertionError):
    """Raised when a known fixture's documented total is not met."""


def process_order(order: dict[str, Any], trace, *, expected_total_cents: int | None = None) -> dict[str, Any]:
    with trace.span("order-validation", kind="agent", input=order) as validation:
        validated = validate_order_tool(order)
        validation.set_output(validated)

    with trace.span("product-lookup", kind="agent", input={"items": order["items"]}) as products_span:
        with trace.tool("lookup_products", args={"skus": [item["sku"] for item in order["items"]]}) as tool:
            products = lookup_products_tool(order["items"])
            tool.set_output(products)
        products_span.set_output({"product_count": len(products)})
    handoff(trace, validation, "product-lookup", target_span_id=products_span.span_id, metadata={"reason": "order_validated"})

    with trace.span("inventory-lookup", kind="agent", input={"items": order["items"]}) as inventory_span:
        with trace.tool("lookup_inventory", args={"skus": [item["sku"] for item in order["items"]]}) as tool:
            inventory = lookup_inventory_tool(order["items"])
            tool.set_output(inventory)
        inventory_span.set_output(inventory)
    handoff(trace, products_span, "inventory-lookup", target_span_id=inventory_span.span_id, metadata={"reason": "products_found"})
    if not inventory["available"]:
        raise OrderInvariantError(f"inventory unavailable: {inventory['shortages']}")

    with trace.span("price-calculation", kind="agent", input={"products": products}) as pricing_span:
        subtotal_cents = calculate_subtotal_tool(products)
        pricing_span.set_output({"subtotal_cents": subtotal_cents})
    handoff(trace, inventory_span, "price-calculation", target_span_id=pricing_span.span_id, metadata={"reason": "inventory_available"})

    with trace.span("discount-application", kind="agent", input={"subtotal_cents": subtotal_cents, "code": order.get("discount_code")}) as discount_span:
        discount = apply_discount_tool(subtotal_cents, order.get("discount_code"))
        discount_span.set_output(discount)
    handoff(trace, pricing_span, "discount-application", target_span_id=discount_span.span_id, metadata={"reason": "subtotal_ready"})

    total_cents = int(discount["total_cents"])
    with trace.span("payment-authorization", kind="agent", input={"customer_id": order["customer_id"], "amount_cents": total_cents}) as payment_span:
        with trace.tool("authorize_payment", args={"customer_id": order["customer_id"], "amount_cents": total_cents}) as tool:
            payment = authorize_payment_tool(order["customer_id"], total_cents)
            tool.set_output(payment)
        payment_span.set_output(payment)
    handoff(trace, discount_span, "payment-authorization", target_span_id=payment_span.span_id, metadata={"reason": "discount_applied"})
    if not payment["authorized"]:
        raise OrderInvariantError("payment authorization failed")

    with trace.span("inventory-reservation", kind="agent", input={"items": order["items"]}) as reservation_span:
        with trace.tool("reserve_inventory", args={"items": order["items"]}) as tool:
            reservation = reserve_inventory_tool(order["items"])
            tool.set_output(reservation)
        reservation_span.set_output(reservation)
    handoff(trace, payment_span, "inventory-reservation", target_span_id=reservation_span.span_id, metadata={"reason": "payment_authorized"})

    with trace.span("order-confirmation", kind="agent", input={"order_id": order["order_id"]}) as confirmation_span:
        with trace.tool("confirm_order", args={"order_id": order["order_id"]}) as tool:
            confirmation = confirm_order_tool(order["order_id"], payment, reservation)
            tool.set_output(confirmation)
        confirmation_span.set_output(confirmation)
    handoff(trace, reservation_span, "order-confirmation", target_span_id=confirmation_span.span_id, metadata={"reason": "reservation_ready"})

    summary = {
        "order_id": order["order_id"],
        "customer_id": order["customer_id"],
        "subtotal_cents": subtotal_cents,
        "discount_cents": int(discount["discount_cents"]),
        "total_cents": total_cents,
        "payment_authorized": payment["authorized"],
        "inventory_reserved": reservation["reserved"],
        "confirmed": confirmation["confirmed"],
    }
    with trace.span("final-order-summary", kind="agent", input={"order_id": order["order_id"]}) as summary_span:
        summary_span.set_output(summary)
    handoff(trace, confirmation_span, "final-order-summary", target_span_id=summary_span.span_id, metadata={"reason": "order_confirmed"})

    if expected_total_cents is not None and total_cents != expected_total_cents:
        with trace.span("pricing-regression-check", kind="agent", input={"expected_cents": expected_total_cents, "actual_cents": total_cents}) as check_span:
            check_span.set_output({"passed": False, "expected_cents": expected_total_cents, "actual_cents": total_cents})
        raise OrderInvariantError(f"expected {expected_total_cents} cents, calculated {total_cents} cents")
    return summary
