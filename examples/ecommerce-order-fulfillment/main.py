from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

SDK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../packages/python-sdk"))
if SDK_ROOT not in sys.path:
    sys.path.insert(0, SDK_ROOT)

try:
    from telemetry import new_scope, workflow_trace
    from workflow import OrderInvariantError, process_order
except ModuleNotFoundError:  # local import when invoked from the repository root
    sys.path.insert(0, os.path.dirname(__file__))
    from telemetry import new_scope, workflow_trace
    from workflow import OrderInvariantError, process_order


FIXTURES: dict[str, dict[str, Any]] = {
    "success": {
        "order_id": "ORDER-SUCCESS-001",
        "customer_id": "customer-demo",
        "items": [{"sku": "SKU-RED", "quantity": 2}, {"sku": "SKU-BLUE", "quantity": 1}],
        "discount_code": "WELCOME10",
        "expected_total_cents": 5850,
    },
    "bug": {
        "order_id": "ORDER-BUG-001",
        "customer_id": "customer-demo",
        "items": [{"sku": "SKU-RED", "quantity": 2}, {"sku": "SKU-BLUE", "quantity": 1}],
        "discount_code": "SPRING20",
        "expected_total_cents": 5200,
    },
}


def main(inputs: dict[str, Any]) -> dict[str, Any]:
    """Task 4 entry point; accepts a bounded JSON object."""

    inputs = inputs or {}
    scenario = str(inputs.get("scenario", "success"))
    if scenario not in FIXTURES:
        raise ValueError(f"unknown scenario: {scenario}")
    fixture = dict(FIXTURES[scenario])
    scope = new_scope()
    metadata = {"demo": "ecommerce-order-fulfillment", "scenario": scenario}
    with workflow_trace(scope, "ecommerce-order-fulfillment", metadata) as trace:
        return process_order(fixture, trace, expected_total_cents=fixture["expected_total_cents"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the deterministic e-commerce SpanTrace demo")
    parser.add_argument("--scenario", choices=sorted(FIXTURES), default="success")
    args = parser.parse_args()
    print(json.dumps(main({"scenario": args.scenario}), sort_keys=True))
