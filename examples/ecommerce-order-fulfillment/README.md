# E-commerce Order Fulfillment

This is a deterministic, offline SpanTrace demo for a conventional order
workflow. It uses local product, inventory, payment, and discount fixtures and
never contacts a real commerce or payment service.

The project is intentionally buggy for debugging practice. The isolated bug is
in `pricing.py:apply_discount`: the `SPRING20` discount is subtracted twice.
For the `bug` fixture, the item subtotal is 6,500 cents, so the correct total is
5,200 cents; the buggy implementation returns 3,900 cents. The correction is to
subtract the discount amount exactly once.

## Architecture

- `main.py` - supported `main(inputs)` entry point and CLI.
- `workflow.py` - validation, lookup, pricing, payment, reservation,
  confirmation, and summary orchestration.
- `catalog.py` - deterministic product and inventory lookup.
- `pricing.py` - price and discount rules; contains the deliberate bug.
- `payments.py` and `fulfillment.py` - deterministic local mocks.
- `telemetry.py` - small helper built on the existing SpanTrace SDK contract.

The default `success` fixture uses `WELCOME10` and completes successfully. The
`bug` fixture uses `SPRING20`, records the incorrect calculation in the trace,
and raises `OrderInvariantError` after the final summary so controlled
execution records a failed workflow. `unit` tests cover the successful path;
`tests/discount_regression.py` is the intentionally failing regression test
until the documented fix is applied.

## Run locally

From the SpanTrace repository root:

```bash
python examples/ecommerce-order-fulfillment/main.py --scenario success
python examples/ecommerce-order-fulfillment/main.py --scenario bug
```

With a running SpanTrace API, set `SPANTRACE_API_URL`, `SPANTRACE_PROJECT_ID`,
and `SPANTRACE_API_KEY`. The application uses the existing manual SDK path and
emits workflow, agent, tool, handoff, and exception events. It also reuses the
worker's active trace when Task 4 invokes it, so the application events remain
on the execution trace.

## Task 3 and Task 4

Import this directory as a ZIP or local archive through the repository import
flow. Select `main.py:main` as the workflow entry point and choose the existing
`callback` or `opentelemetry` adapter; the entry point itself uses the tested
manual SDK contract. The Task 4 input is a JSON object such as:

```json
{"scenario":"success"}
```

Use `{"scenario":"bug"}` to observe the failed pricing invariant. The
controlled worker does not install dependencies or run shell commands, and this
project needs no dependency beyond the SDK already present in the worker image.

## Regression verification

The regression test is deliberately kept separate from the passing unit suite:

```bash
python -m unittest discover -s examples/ecommerce-order-fulfillment/tests -p 'test_workflow.py'
python -m unittest discover -s examples/ecommerce-order-fulfillment/tests -p 'discount_regression.py'
```

The second command fails before the fix because it expects 5,200 cents and
receives 3,900 cents. In an isolated copy, change the marked `SPRING20` branch
in `pricing.py` to return `subtotal_cents - discount_cents`, then rerun the
regression test and the `bug` workflow. The corrected workflow returns a valid
5,200-cent total instead of raising the invariant error.
