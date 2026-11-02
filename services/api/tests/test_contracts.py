from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.contracts import ContractValidationError, evaluate_definition, parse_contract_document


def auth(project):
    return {"X-API-Key": project["api_key"]}


def zip_bytes(files: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def test_contract_parser_accepts_all_supported_predicates():
    definitions = parse_contract_document(
        """
contracts:
  - id: order.same
    description: Values match.
    predicate: eq
    left: output.order.total
    right: output.order.expected
  - id: order.within
    description: Total is within the limit.
    predicate: lte
    left: output.order.total
    right: output.order.limit
  - id: order.minimum
    description: Total is above the minimum.
    predicate: gte
    left: output.order.total
    right: output.order.minimum
  - id: order.sum
    description: Parts add up.
    predicate: sum_equals
    terms: output.order.items[*].cost
    target: output.order.total
    tolerance: 0.01
  - id: order.difference
    description: Discount is applied once.
    predicate: difference_equals
    minuend: output.order.subtotal
    subtrahend: output.order.discount
    target: output.order.total
    tolerance: 0
"""
    )
    assert [item.predicate for item in definitions] == ["eq", "lte", "gte", "sum_equals", "difference_equals"]
    assert definitions[3].arguments["terms"] == "output.order.items[*].cost"


@pytest.mark.parametrize(
    ("document", "contract_id", "problem"),
    [
        ("contracts:\n  - id: bad.unknown\n    description: x\n    predicate: nope\n    left: output.a\n    right: output.b\n", "bad.unknown", "unknown predicate"),
        ("contracts:\n  - id: bad.missing\n    description: x\n    predicate: lte\n    left: output.a\n", "bad.missing", "missing argument 'right'"),
        ("contracts:\n  - id: bad.path\n    description: x\n    predicate: eq\n    left: result.a\n    right: output.b\n", "bad.path", "must be a path starting with output."),
        ("contracts:\n  - id: bad.tolerance\n    description: x\n    predicate: sum_equals\n    terms: output.items[*].cost\n    target: output.total\n    tolerance: -1\n", "bad.tolerance", "negative tolerance"),
    ],
)
def test_contract_parser_names_each_invalid_contract(document: str, contract_id: str, problem: str):
    with pytest.raises(ContractValidationError) as error:
        parse_contract_document(document)
    assert contract_id in str(error.value)
    assert problem in str(error.value)


def test_contract_evaluator_passes_and_fails():
    definition = parse_contract_document(
        """
contracts:
  - id: order.total
    description: Total matches parts.
    predicate: sum_equals
    terms: output.items[*].cost
    target: output.total
    tolerance: 0.01
"""
    )[0]
    passing = evaluate_definition(definition, {"items": [{"cost": 2}, {"cost": 3}], "total": 5})
    failing = evaluate_definition(definition, {"items": [{"cost": 2}, {"cost": 3}], "total": 6})
    assert passing["status"] == "pass"
    assert failing["status"] == "fail"


def test_contract_evaluator_is_inconclusive_for_missing_and_non_numeric_values():
    definition = parse_contract_document(
        """
contracts:
  - id: order.total
    description: Total is valid.
    predicate: eq
    left: output.total
    right: output.expected
"""
    )[0]
    missing = evaluate_definition(definition, {"total": 5})
    non_numeric = evaluate_definition(definition, {"total": 5, "expected": "5"})
    assert missing["status"] == "inconclusive"
    assert non_numeric["status"] == "inconclusive"


def test_contract_api_stores_approvals_and_creates_draft_version(client, project):
    created = client.post(
        "/v1/contracts",
        headers=auth(project),
        json={"id": "order.total", "description": "Total matches.", "predicate": "eq", "left": "output.total", "right": "output.expected"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["contract"]["status"] == "draft"
    approved = client.post("/v1/contracts/order.total/approve", headers=auth(project))
    assert approved.status_code == 200
    assert approved.json()["contract"]["approved_by"]
    edited = client.put(
        "/v1/contracts/order.total",
        headers=auth(project),
        json={"id": "order.total", "description": "Total remains within the limit.", "predicate": "lte", "left": "output.total", "right": "output.limit"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["contract"]["version"] == 2
    assert edited.json()["contract"]["status"] == "draft"
    listed = client.get("/v1/contracts", headers=auth(project))
    assert listed.status_code == 200
    assert listed.json()["items"][0]["status"] == "draft"


def test_imported_contracts_start_as_draft(client, project):
    files = {
        ".spantrace/contracts.yaml": "contracts:\n  - id: demo.total\n    description: Total matches.\n    predicate: eq\n    left: output.total\n    right: output.expected\n",
        "workflow.py": "def main(inputs):\n    return {'total': 1, 'expected': 1}\n",
    }
    imported = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("demo.zip", zip_bytes(files), "application/zip")})
    assert imported.status_code == 201, imported.text
    contracts = client.get("/v1/contracts", headers=auth(project)).json()["items"]
    assert contracts[0]["id"] == "demo.total"
    assert contracts[0]["status"] == "draft"
