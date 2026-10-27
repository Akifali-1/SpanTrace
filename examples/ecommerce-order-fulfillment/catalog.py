from __future__ import annotations

from typing import Any


PRODUCTS: dict[str, dict[str, Any]] = {
    "SKU-RED": {"name": "Trail Jacket", "unit_price_cents": 2500, "available_units": 12},
    "SKU-BLUE": {"name": "Travel Mug", "unit_price_cents": 1500, "available_units": 20},
}


def validate_order(order: dict[str, Any]) -> dict[str, Any]:
    if not order.get("customer_id"):
        raise ValueError("customer_id is required")
    items = order.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("at least one order item is required")
    for item in items:
        if item.get("sku") not in PRODUCTS:
            raise ValueError(f"unknown product: {item.get('sku')}")
        if not isinstance(item.get("quantity"), int) or item["quantity"] <= 0:
            raise ValueError("item quantity must be a positive integer")
    return {"customer_id": order["customer_id"], "item_count": len(items), "valid": True}


def validate_order_tool(order: dict[str, Any]) -> dict[str, Any]:
    return validate_order(order)


def lookup_products(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "sku": item["sku"],
            "name": PRODUCTS[item["sku"]]["name"],
            "quantity": item["quantity"],
            "unit_price_cents": PRODUCTS[item["sku"]]["unit_price_cents"],
            "available_units": PRODUCTS[item["sku"]]["available_units"],
        }
        for item in items
    ]


def lookup_products_tool(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return lookup_products(items)


def lookup_inventory(items: list[dict[str, Any]]) -> dict[str, Any]:
    shortages = [
        {"sku": item["sku"], "requested": item["quantity"], "available": PRODUCTS[item["sku"]]["available_units"]}
        for item in items
        if item["quantity"] > PRODUCTS[item["sku"]]["available_units"]
    ]
    return {"available": not shortages, "shortages": shortages}


def lookup_inventory_tool(items: list[dict[str, Any]]) -> dict[str, Any]:
    return lookup_inventory(items)
