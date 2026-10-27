from __future__ import annotations

from typing import Any


DISCOUNT_RULES = {"WELCOME10": 10, "SPRING20": 20}


def calculate_subtotal(products: list[dict[str, Any]]) -> int:
    return sum(item["quantity"] * item["unit_price_cents"] for item in products)


def calculate_subtotal_tool(products: list[dict[str, Any]]) -> int:
    return calculate_subtotal(products)


def apply_discount(subtotal_cents: int, discount_code: str | None) -> dict[str, int | str | None]:
    percent = DISCOUNT_RULES.get(discount_code or "", 0)
    discount_cents = subtotal_cents * percent // 100
    if discount_code == "SPRING20":
        # INTENTIONAL DEMO BUG: this rule is applied twice. The discount
        # contract requires one subtraction from the subtotal.
        total_cents = subtotal_cents - discount_cents - discount_cents
    else:
        total_cents = subtotal_cents - discount_cents
    return {
        "discount_code": discount_code,
        "discount_percent": percent,
        "discount_cents": discount_cents,
        "total_cents": total_cents,
    }


def apply_discount_tool(subtotal_cents: int, discount_code: str | None) -> dict[str, int | str | None]:
    return apply_discount(subtotal_cents, discount_code)
