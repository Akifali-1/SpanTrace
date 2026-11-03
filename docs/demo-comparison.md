# Deterministic demo comparison

The two documented demos were run five times each with their deterministic success fixtures. The demos use only in-process recorded responses; no model or external service was called.

Docker live worker runs were not run because the Docker daemon/worker image was unavailable in this environment. The table below records the local deterministic comparison evidence.

| Demo | Runs | Contract | Results | Stability label |
| --- | ---: | --- | --- | --- |
| `ecommerce-order-fulfillment` | 5 | `order.discount_applied_once` | pass, pass, pass, pass, pass | `stable-pass` |
| `travel-planner-multi-agent` | 5 | `travel.total_matches_line_items` | pass, pass, pass, pass, pass | `stable-pass` |
| `travel-planner-multi-agent` | 5 | `travel.total_within_budget` | pass, pass, pass, pass, pass | `stable-pass` |
