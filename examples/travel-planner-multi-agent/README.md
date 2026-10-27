# Travel Planner Multi-Agent

This is the larger deterministic SpanTrace workflow. It runs fully offline
against local transport, accommodation, and activity fixtures and models a
coordinator handing work to several specialist agents.

The project is intentionally buggy for debugging practice. The isolated bug is
in `budget_agent.py:calculate_budget`: for the named `bug` fixture, transport
prices are represented in cents, but the Budget Agent divides the transport
amount by 100 before adding it to the all-cents total. The ordinary `success`
fixture follows the same contract correctly; the distinct `bug` fixture has:

```text
transport       72,000 cents
accommodation 150,000 cents
activities      30,000 cents
true total     252,000 cents
budget         240,000 cents
```

The buggy Budget Agent reports 180,720 cents and approves the itinerary. The
Validation Agent independently recomputes the original itemized costs, detects
that the true total exceeds the budget, and fails the workflow. The correction
is one line: add `transport["price_cents"]` without dividing by 100.

## Architecture and topology

- `main.py` - supported `main(inputs)` entry point and CLI.
- `workflow.py` - Trip Coordinator, branch convergence, budget decision,
  adjustment pass, itinerary assembly, and final validation.
- `transport_agent.py` - mock transport search and selection.
- `accommodation_agent.py` - mock hotel selection and nightly-cost math.
- `activities_agent.py` - preference matching and activity-cost calculation.
- `budget_agent.py` - aggregation and budget decision; contains the deliberate
  bug.
- `itinerary_agent.py` and `validation_agent.py` - final assembly and
  independent requirement validation.
- `models.py` and `fixtures.py` - typed request/response contracts and local
  fixture data.
- `telemetry.py` - manual SpanTrace spans, tools, parent relationships, and
  target-aware handoffs.

The real execution path is sequential: the three specialist branches execute
one after another, converge at the Budget Agent, and may enter a real
adjustment pass that invokes the selected specialists again. It does not claim
parallel execution. `success` completes within budget; `bug` is the
under-counting demonstration; `adjustment` exercises the over-budget branch
and returns an explicit validation failure with its lower-budget fixture.

## Price contract

Every price and budget in this project is an integer number of cents. The
transport, accommodation, and activities agents all return cents. The Budget
Agent is the only deliberately defective consumer in the buggy source.

## Run locally

From the SpanTrace repository root:

```bash
python examples/travel-planner-multi-agent/main.py --scenario success
python examples/travel-planner-multi-agent/main.py --scenario bug
python examples/travel-planner-multi-agent/main.py --scenario adjustment
```

With a running SpanTrace API, set `SPANTRACE_API_URL`, `SPANTRACE_PROJECT_ID`,
and `SPANTRACE_API_KEY`. The workflow uses the existing manual SDK contract and
records coordinator/agent/tool spans, explicit parent-child IDs, handoffs,
budget decisions, adjustment attempts, validation output, and exceptions. When
Task 4 invokes `main(inputs)`, the workflow reuses the worker's active trace.

## Task 3 and Task 4

Import this directory through the existing repository import flow. Task 3 can
discover the `main` entry point, the specialist agent functions, tool functions,
SpanTrace instrumentation, and their source evidence. Select `main.py:main` and
an existing adapter in the generated configuration. Task 4 inputs are:

```json
{"scenario":"success"}
```

Use `{"scenario":"bug"}` for the under-counting failure graph. No package
installation, network service, credentials, or external API is required.

The analyzer intentionally remains conservative across module boundaries: the
runtime trace is authoritative for the executed parent and handoff graph, while
Task 3 reports source relationships it can prove from each Python file.

## Regression verification

The passing unit suite is separate from the intentional regression test:

```bash
python -m unittest discover -s examples/travel-planner-multi-agent/tests -p 'test_workflow.py'
python -m unittest discover -s examples/travel-planner-multi-agent/tests -p 'budget_regression.py'
```

The second command fails before the fix because it expects 252,000 cents and
receives 180,720 cents. In an isolated copy, fix the marked conversion in
`budget_agent.py`, rerun the regression test, then run the `bug` workflow again;
the corrected implementation enters the real adjustment pass and completes
with a budget-compliant itinerary.
