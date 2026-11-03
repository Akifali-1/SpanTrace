"""Run the deterministic demos five times and record contract stability."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))
from app.contracts import evaluate_definition, load_contracts_from_snapshot, label_contract_stability  # noqa: E402


DEMOS = {
    "ecommerce-order-fulfillment": {
        "main": ROOT / "examples" / "ecommerce-order-fulfillment" / "main.py",
        "contracts": ROOT / "examples" / "ecommerce-order-fulfillment",
        "args": ["--scenario", "success"],
    },
    "travel-planner-multi-agent": {
        "main": ROOT / "examples" / "travel-planner-multi-agent" / "main.py",
        "contracts": ROOT / "examples" / "travel-planner-multi-agent",
        "args": ["--scenario", "success"],
    },
}


def run_demo(main: Path, args: list[str]) -> dict[str, Any]:
    result = subprocess.run([sys.executable, str(main), *args], cwd=main.parent, capture_output=True, text=True, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def main() -> int:
    rows: list[dict[str, Any]] = []
    for name, spec in DEMOS.items():
        definitions = load_contracts_from_snapshot(spec["contracts"])
        outputs = [run_demo(spec["main"], spec["args"]) for _ in range(5)]
        outcomes = {definition.id: [evaluate_definition(definition, output)["status"] for output in outputs] for definition in definitions}
        labels = {contract_id: label_contract_stability([{"status": status} for status in statuses]) for contract_id, statuses in outcomes.items()}
        rows.append({"demo": name, "scenario": "success", "runs": 5, "contract_results": outcomes, "stability_labels": labels})

    lines = [
        "# Deterministic demo comparison",
        "",
        "The two documented demos were run five times each with their deterministic success fixtures. The demos use only in-process recorded responses; no model or external service was called.",
        "",
        "Docker live worker runs were not run because the Docker daemon/worker image was unavailable in this environment. The table below records the local deterministic comparison evidence.",
        "",
        "| Demo | Runs | Contract | Results | Stability label |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for row in rows:
        for contract_id, statuses in row["contract_results"].items():
            lines.append(f"| `{row['demo']}` | {row['runs']} | `{contract_id}` | {', '.join(statuses)} | `{row['stability_labels'][contract_id] or 'unavailable'}` |")
    (ROOT / "docs" / "demo-comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
