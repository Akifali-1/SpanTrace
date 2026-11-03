# Developer contracts

Contracts are developer-authored correctness rules stored in the imported repository at `.spantrace/contracts.yaml`. Imported contracts are drafts until a project reviewer approves them through the API or dashboard. Only approved contracts are evaluated against controlled execution output.

```yaml
contracts:
  - id: order.discount_applied_once
    description: The order total must equal subtotal minus discount.
    predicate: difference_equals
    minuend: output.subtotal_cents
    subtrahend: output.discount_cents
    target: output.total_cents
    tolerance: 0.01
```

Paths must start with `output.` and use dotted object properties. `sum_equals` may use `[*]` to project a list, for example `output.items[*].cost`. Span-level paths are not supported.

Supported predicates:

- `eq`: `left` equals `right`.
- `lte`: `left` is less than or equal to `right`.
- `gte`: `left` is greater than or equal to `right`.
- `sum_equals`: the numeric sum at `terms` equals `target` within `tolerance`.
- `difference_equals`: `minuend - subtrahend` equals `target` within `tolerance`.

Missing paths and non-numeric values produce `inconclusive`, never a pass. Tolerance must be numeric and non-negative. Contract versions are immutable after approval; editing an approved contract creates a new draft version.

Regression generation requires a recorded input, an immutable source snapshot, and recorded tool/model responses. If those deterministic replay prerequisites are unavailable, the generated test is blocked with the reason rather than producing a potentially flaky test.
