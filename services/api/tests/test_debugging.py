from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.db import SessionLocal
from app.main import execution_coordinator
from app.models import ExecutionRun


def zip_bytes(files: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def auth(project):
    return {"X-API-Key": project["api_key"]}


def setup_failed_execution(client, project, monkeypatch):
    files = {
        "main.py": "def main(inputs):\n    from pricing import apply_discount\n    result = apply_discount(6500, inputs.get('code', 'SPRING20'))\n    if result['total_cents'] != 5200:\n        raise AssertionError(f\"expected 5200 cents, calculated {result['total_cents']} cents\")\n    return result\n",
        "pricing.py": "def apply_discount(subtotal_cents, discount_code):\n    discount_cents = subtotal_cents * 20 // 100\n    total_cents = subtotal_cents - discount_cents - discount_cents\n    return {'discount_code': discount_code, 'discount_cents': discount_cents, 'total_cents': total_cents}\n",
        "tests/test_workflow.py": "import unittest\n\nclass WorkflowTests(unittest.TestCase):\n    def test_fixture_contract(self):\n        self.assertEqual(2 + 2, 4)\n",
    }
    imported = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("debug.zip", zip_bytes(files), "application/zip")})
    assert imported.status_code == 201, imported.text
    analysis = imported.json()["analysis"]
    entry = next(item for item in analysis["findings"] if item["kind"] == "workflow_entry")
    config = client.post(f"/v1/repositories/{analysis['id']}/config", headers=auth(project), json={"workflow_entry_point_ids": [entry["finding_id"]], "adapter_ids": ["callback"]})
    assert config.status_code == 201, config.text
    monkeypatch.setattr(execution_coordinator, "submit", lambda *_args: None)
    created = client.post(f"/v1/repositories/{analysis['id']}/executions", headers=auth(project), json={"workflow_entry_point_id": entry["finding_id"], "configuration_id": config.json()["configuration"]["id"], "inputs": {"scenario": "bug", "secret": "do-not-leak"}, "idempotency_key": "debug-original"})
    assert created.status_code == 202, created.text
    execution_id = created.json()["execution"]["id"]
    with SessionLocal() as db:
        execution = db.get(ExecutionRun, execution_id)
        execution.status = "failed"
        execution.failure_category = "workflow_exception"
        execution.logs_text = 'Traceback (most recent call last):\n  File "/workspace/source/main.py", line 5, in main\n    raise AssertionError("expected 5200 cents, calculated 3900 cents")\nAssertionError: expected 5200 cents, calculated 3900 cents\napi_key=super-secret'
        execution.completed_at = datetime.utcnow()
        db.commit()
    trace_id = created.json()["execution"]["trace_id"]
    now = datetime.now(timezone.utc).isoformat()
    ingested = client.post("/v1/ingest/events", headers=auth(project), json={"events": [{"event_id": "debug-failed", "trace_id": trace_id, "event_type": "exception", "status": "failed", "occurred_at": now, "error_type": "AssertionError", "error_details": "expected 5200 cents, calculated 3900 cents"}]})
    assert ingested.status_code == 200, ingested.text
    return analysis, execution_id, trace_id


def test_investigation_evidence_reproduction_and_project_scope(client, project, monkeypatch):
    _analysis, execution_id, trace_id = setup_failed_execution(client, project, monkeypatch)
    created = client.post(f"/v1/executions/{execution_id}/investigations", headers=auth(project), json={"name": "Discount failure"})
    assert created.status_code == 201, created.text
    investigation = created.json()["investigation"]
    assert investigation["failure_category"] == "assertion_failure"
    assert investigation["root_causes"][0]["source"]["file_path"] == "pricing.py"
    assert "super-secret" not in str(investigation)
    def repeat_original(execution_id, _token, _inputs):
        with SessionLocal() as db:
            execution = db.get(ExecutionRun, execution_id)
            execution.status = "failed"
            execution.failure_category = "workflow_exception"
            execution.completed_at = datetime.utcnow()
            execution.logs_text = "AssertionError: expected 5200 cents, calculated 3900 cents"
            db.commit()
    monkeypatch.setattr(execution_coordinator, "submit", repeat_original)
    reproduction = client.post(f"/v1/investigations/{investigation['id']}/reproduction", headers=auth(project), json={})
    assert reproduction.status_code == 202, reproduction.text
    reproduced = client.get(f"/v1/investigations/{investigation['id']}", headers=auth(project)).json()
    assert reproduced["reproductions"][0]["status"] == "reproduced"
    other = client.post("/v1/projects", json={"name": "Other debug project"}).json()
    assert client.get(f"/v1/investigations/{investigation['id']}", headers=auth(other)).status_code == 404
    assert client.post(f"/v1/runs/{trace_id}/investigations", headers=auth(project), json={"name": "same"}).status_code == 201


def test_regression_patch_review_and_verified_fix_require_real_steps(client, project, monkeypatch):
    _analysis, execution_id, _trace_id = setup_failed_execution(client, project, monkeypatch)
    created = client.post(f"/v1/executions/{execution_id}/investigations", headers=auth(project), json={"name": "Discount fix"})
    investigation_id = created.json()["investigation"]["id"]

    results = [
        {"status": "failed", "exit_code": 1, "failures": ["test_spring_discount_is_applied_once"], "logs": "AssertionError: 3900 != 5200"},
        {"status": "failed", "exit_code": 1, "failures": ["test_spring_discount_is_applied_once"], "logs": "AssertionError: 3900 != 5200"},
        {"status": "passed", "exit_code": 0, "tests_run": 1, "logs": "OK"},
        {"status": "passed", "exit_code": 0, "tests_run": 1, "logs": "OK"},
    ]
    monkeypatch.setattr("app.main.run_isolated_unittest", lambda *_args, **_kwargs: results.pop(0))
    generated = client.post(f"/v1/investigations/{investigation_id}/regression-test", headers=auth(project))
    assert generated.status_code == 201, generated.text
    artifact = generated.json()["test"]
    assert artifact["status"] == "validated"
    assert artifact["original_result"]["status"] == "failed"

    proposed = client.post(f"/v1/investigations/{investigation_id}/patch", headers=auth(project))
    assert proposed.status_code == 201, proposed.text
    patch = proposed.json()["patch"]
    assert "-    total_cents = subtotal_cents - discount_cents - discount_cents" in patch["diff"]
    assert "+    total_cents = subtotal_cents - discount_cents" in patch["diff"]
    assert client.post(f"/v1/investigations/{investigation_id}/patches/{patch['id']}/decision", headers=auth(project), json={"decision": "approved"}).status_code == 200

    def complete_patched(execution_id, _token, _inputs):
        with SessionLocal() as db:
            execution = db.get(ExecutionRun, execution_id)
            execution.status = "succeeded"
            execution.exit_code = 0
            execution.completed_at = datetime.utcnow()
            execution.result_json = {"output": {"total_cents": 5200}}
            db.commit()

    monkeypatch.setattr(execution_coordinator, "submit", complete_patched)
    verified = client.post(f"/v1/investigations/{investigation_id}/verify", headers=auth(project), json={"run_controlled_rerun": True})
    assert verified.status_code == 202, verified.text
    assert verified.json()["verification"]["status"] == "verified", verified.json()
    detail = client.get(f"/v1/investigations/{investigation_id}", headers=auth(project)).json()
    assert detail["status"] == "verified"
    assert detail["verifications"][0]["report"]["comparison"]["controlled_rerun_passed"] is True
    with SessionLocal() as db:
        analysis = db.query(ExecutionRun).filter(ExecutionRun.id == execution_id).first().analysis
        original = Path(analysis.source_path) / "pricing.py"
        assert "- discount_cents - discount_cents" in original.read_text(encoding="utf-8")


def test_unverified_test_cannot_be_marked_verified(client, project, monkeypatch):
    _analysis, execution_id, _trace_id = setup_failed_execution(client, project, monkeypatch)
    investigation_id = client.post(f"/v1/executions/{execution_id}/investigations", headers=auth(project), json={"name": "Bad verification"}).json()["investigation"]["id"]
    monkeypatch.setattr("app.main.run_isolated_unittest", lambda *_args, **_kwargs: {"status": "passed", "exit_code": 0, "tests_run": 1, "logs": "unexpected pass"})
    generated = client.post(f"/v1/investigations/{investigation_id}/regression-test", headers=auth(project))
    assert generated.json()["test"]["status"] == "rejected"
    assert client.post(f"/v1/investigations/{investigation_id}/patch", headers=auth(project)).status_code == 409
