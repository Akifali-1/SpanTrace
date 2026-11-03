# External repository validation

## Repository

- **Repository:** [nripankadas07/agent-framework](https://github.com/nripankadas07/agent-framework)
- **Commit:** `803309e343ba62528f9dc75f083ae8058d92b1e7`
- **License:** MIT (`.external-validation/LICENSE`)
- **Core package size:** 607 Python source lines across `agent_framework/`
- **Credentials:** none required for the documented deterministic demo
- **Upstream tests:** 37 passed

The clone was made once at `.external-validation/` and is ignored by Git. The
checkout contains a validation-only adapter, `spantrace_validation.py`, which
returns the documented no-key demo's structured result. It does not change the
upstream core package. The checkout also contains the contracts at
`.spantrace/contracts.yaml` so the existing SpanTrace archive importer can load
them.

## Import and approval

The checkout was archived locally and imported through the existing
`POST /v1/repositories/import/zip` path. The analysis completed successfully
and selected `spantrace_validation.py:main` as the workflow entry point. Both
imported contracts were approved through the existing contract approval API.

The isolated worker execution was **not run** because the Docker daemon and
`spantrace-worker:0.1.0` image were unavailable in this environment. The API
preflight and contract evaluation were exercised with a saved successful
execution result, without claiming that as a live worker run.

## Contracts and results

The contracts use only supported predicates and `output.*` paths:

| Contract | Predicate | Saved API result | Five-run result sequence | Stability label | Reason |
| --- | --- | --- | --- | --- | --- |
| `demo.completes_successfully` | `gte(output.steps, output.minimum_steps)` | pass | pass, pass, pass, pass, pass | `stable-pass` | The documented adapter returned 2 steps and the minimum is 2. |
| `demo.uses_documented_two_step_trace` | `eq(output.steps, output.expected_steps)` | pass | pass, pass, pass, pass, pass | `stable-pass` | The documented example shows a two-step tool trace; the adapter returned 2. |

The five-run comparison used the deterministic planner and arithmetic tool from
the documented example, with no model call, API key, or external service.

## Gaps

- No live isolated worker result or network smoke result can be claimed until a
  Docker daemon and the worker image are available.
- The saved API validation contains one execution, so its API stability count
  is 1 and its live API stability label is pending; the recorded five-run
  labels above come from the saved deterministic adapter outputs.
- The validation adapter is local evidence for the documented example and is
  not part of the upstream commit.
