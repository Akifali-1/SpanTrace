from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from app.execution import transition_status
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


def setup_analysis(client, project):
    source = '''from spantrace import SpanTrace

def main(inputs):
    return {"echo": inputs.get("value", "default")}
'''
    imported = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("fixture.zip", zip_bytes({"workflow.py": source}), "application/zip")})
    assert imported.status_code == 201, imported.text
    analysis = imported.json()["analysis"]
    entry = next(item for item in analysis["findings"] if item["kind"] == "workflow_entry")
    saved = client.post(
        f"/v1/repositories/{analysis['id']}/config",
        headers=auth(project),
        json={"workflow_entry_point_ids": [entry["finding_id"]], "component_ids": [], "adapter_ids": ["callback"]},
    )
    assert saved.status_code == 201, saved.text
    return analysis, entry, saved.json()["configuration"]


def test_execution_preflight_persists_and_is_idempotent(client, project, monkeypatch):
    analysis, entry, configuration = setup_analysis(client, project)
    monkeypatch.setattr(execution_coordinator, "submit", lambda *_args: None)
    payload = {
        "workflow_entry_point_id": entry["finding_id"],
        "configuration_id": configuration["id"],
        "inputs": {"value": "hello"},
        "idempotency_key": "same-start",
    }
    first = client.post(f"/v1/repositories/{analysis['id']}/executions", headers=auth(project), json=payload)
    assert first.status_code == 202, first.text
    execution = first.json()["execution"]
    assert execution["status"] == "queued"
    assert execution["source_revision"] == analysis["source_revision"]
    second = client.post(f"/v1/repositories/{analysis['id']}/executions", headers=auth(project), json=payload)
    assert second.status_code == 202
    assert second.json()["reused"] is True
    assert second.json()["execution"]["id"] == execution["id"]


def test_execution_rejects_stale_config_and_project_cross_access(client, project, monkeypatch):
    analysis, entry, configuration = setup_analysis(client, project)
    monkeypatch.setattr(execution_coordinator, "submit", lambda *_args: None)
    other = client.post("/v1/projects", json={"name": "Other execution project"}).json()
    denied = client.get(f"/v1/executions/not-owned", headers=auth(other))
    assert denied.status_code == 404
    stale = client.post(
        f"/v1/repositories/{analysis['id']}/executions",
        headers=auth(project),
        json={"workflow_entry_point_id": entry["finding_id"], "configuration_id": "not-a-config", "inputs": {}},
    )
    assert stale.status_code == 404


def test_execution_token_endpoint_does_not_accept_project_key(client, project, monkeypatch):
    analysis, entry, configuration = setup_analysis(client, project)
    monkeypatch.setattr(execution_coordinator, "submit", lambda *_args: None)
    created = client.post(
        f"/v1/repositories/{analysis['id']}/executions",
        headers=auth(project),
        json={"workflow_entry_point_id": entry["finding_id"], "configuration_id": configuration["id"], "inputs": {}},
    )
    execution_id = created.json()["execution"]["id"]
    rejected = client.post(
        f"/v1/executions/{execution_id}/events",
        headers={"X-Execution-Token": project["api_key"]},
        json={"events": [{"event_id": "spoof", "trace_id": created.json()["execution"]["trace_id"], "event_type": "run_started", "occurred_at": "2026-01-01T00:00:00Z"}]},
    )
    assert rejected.status_code == 401


def test_execution_token_is_scoped_to_its_execution_and_inputs_are_bounded(client, project, monkeypatch):
    analysis, entry, configuration = setup_analysis(client, project)
    captured: dict[str, str] = {}

    def capture_submit(execution_id, token, inputs):
        captured[execution_id] = token

    monkeypatch.setattr(execution_coordinator, "submit", capture_submit)
    common = {"workflow_entry_point_id": entry["finding_id"], "configuration_id": configuration["id"], "inputs": {"secret": "do-not-return"}}
    first = client.post(f"/v1/repositories/{analysis['id']}/executions", headers=auth(project), json={**common, "idempotency_key": "token-one"})
    second = client.post(f"/v1/repositories/{analysis['id']}/executions", headers=auth(project), json={**common, "idempotency_key": "token-two"})
    assert first.status_code == 202 and second.status_code == 202
    first_id = first.json()["execution"]["id"]
    second_id = second.json()["execution"]["id"]
    assert first.json()["execution"]["input"]["secret"] == "[REDACTED]"
    cross_run = client.post(
        f"/v1/executions/{second_id}/events",
        headers={"X-Execution-Token": captured[first_id]},
        json={"events": [{"event_id": "cross-run", "trace_id": second.json()["execution"]["trace_id"], "event_type": "run_started", "occurred_at": "2026-01-01T00:00:00Z"}]},
    )
    assert cross_run.status_code == 401

    oversized = client.post(
        f"/v1/repositories/{analysis['id']}/executions",
        headers=auth(project),
        json={"workflow_entry_point_id": entry["finding_id"], "configuration_id": configuration["id"], "inputs": {"value": "x" * 70_000}, "idempotency_key": "oversized-input"},
    )
    assert oversized.status_code == 413


def test_missing_docker_is_reported_as_infrastructure_error(client, project, monkeypatch):
    analysis, entry, configuration = setup_analysis(client, project)
    monkeypatch.setattr("app.execution.shutil.which", lambda _name: None)
    def run_without_queue(execution_id, token, inputs):
        execution_coordinator._tokens[execution_id] = token
        execution_coordinator._inputs[execution_id] = inputs
        execution_coordinator._run(execution_id)
    monkeypatch.setattr(execution_coordinator, "submit", run_without_queue)
    created = client.post(
        f"/v1/repositories/{analysis['id']}/executions",
        headers=auth(project),
        json={"workflow_entry_point_id": entry["finding_id"], "configuration_id": configuration["id"], "inputs": {}},
    )
    assert created.status_code == 202
    detail = client.get(f"/v1/executions/{created.json()['execution']['id']}", headers=auth(project)).json()
    assert detail["status"] == "infrastructure_error"
    assert detail["failure_category"] == "docker_unavailable"


def test_execution_status_transitions_reject_invalid_terminal_overwrite():
    execution = ExecutionRun(
        status="queued",
        project_id="p",
        analysis_id="a",
        configuration_id="c",
        source_revision="r",
        archive_fingerprint="f",
        entry_finding_id="e",
        entry_file_path="workflow.py",
        entry_symbol="main",
        trace_id="t",
        idempotency_key="i",
        input_fingerprint="i",
        execution_token_hash="h",
        execution_token_prefix="p",
        timeout_seconds=10,
        memory_mb=64,
        cpu_limit="1",
        pids_limit=16,
    )
    transition_status(execution, "starting")
    transition_status(execution, "running")
    transition_status(execution, "succeeded")
    try:
        transition_status(execution, "failed")
    except ValueError:
        pass
    else:
        raise AssertionError("Terminal execution states must not be overwritten")
