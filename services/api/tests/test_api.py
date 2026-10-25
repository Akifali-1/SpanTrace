from datetime import datetime, timedelta, timezone


def event(event_id: str, trace_id: str = "trace-1", **overrides):
    value = {
        "event_id": event_id,
        "trace_id": trace_id,
        "event_type": "agent_span",
        "kind": "agent",
        "status": "succeeded",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "agent_name": "planner",
        "output": {"ok": True},
    }
    value.update(overrides)
    return value


def auth(project):
    return {"X-API-Key": project["api_key"]}


def test_ingest_is_idempotent_and_project_scoped(client, project):
    headers = auth(project)
    payload = {"events": [event("e-1"), event("e-2", parent_span_id="e-1")]}
    response = client.post("/v1/ingest/events", headers=headers, json=payload)
    assert response.status_code == 200
    assert response.json()["accepted"] == 2
    duplicate = client.post("/v1/ingest/events", headers=headers, json=payload)
    assert duplicate.json()["duplicates"] == 2
    runs = client.get("/v1/runs", headers=headers)
    assert runs.status_code == 200
    assert runs.json()["items"][0]["event_count"] == 2

    other = client.post("/v1/projects", json={"name": "Other project"}).json()
    denied = client.get("/v1/runs/trace-1", headers=auth(other))
    assert denied.status_code == 404


def test_invalid_key_and_invalid_event_are_rejected(client, project):
    assert client.get("/v1/runs", headers={"X-API-Key": "ask_invalid"}).status_code == 401
    invalid = client.post("/v1/ingest/events", headers=auth(project), json={"events": [{"event_id": "x"}]})
    assert invalid.status_code == 422


def test_incident_evidence_and_regression_case(client, project):
    headers = auth(project)
    now = datetime.now(timezone.utc)
    events = [
        event("approval", event_type="approval", kind="policy", agent_name="approval-policy", occurred_at=now.isoformat(), output={"approval_state": "pending"}),
        event("booking-tool", event_type="tool_call", kind="tool", agent_name="booking", tool_name="create_reservation", tool_args={"approval_state": "pending"}, tool_result={"reservation_id": "MOCK-1", "created": True}, occurred_at=(now + timedelta(seconds=1)).isoformat()),
        event("done", event_type="run_completed", kind="workflow", status="succeeded", occurred_at=(now + timedelta(seconds=2)).isoformat()),
    ]
    assert client.post("/v1/ingest/events", headers=headers, json={"events": events}).status_code == 200
    detail = client.get("/v1/runs/trace-1", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["incidents"][0]["violating_event_id"] == "booking-tool"
    assert "approval state was pending" in body["incidents"][0]["evidence"][0]["fact"]
    case = client.post("/v1/runs/trace-1/regression-case", headers=headers, json={"name": "Approval regression"})
    assert case.status_code == 201
    case_id = case.json()["id"]
    failed = client.post(f"/v1/regression-cases/{case_id}/run", headers=headers, json={"fixed": False})
    passed = client.post(f"/v1/regression-cases/{case_id}/run", headers=headers, json={"fixed": True})
    assert failed.json()["passed"] is False
    assert passed.json()["passed"] is True


def test_filters_and_health(client, project):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/readiness").json()["status"] == "ready"
    headers = auth(project)
    client.post("/v1/ingest/events", headers=headers, json={"events": [event("f-1", trace_id="failed", status="failed", agent_name="booking")]})
    assert client.get("/v1/runs?status=failed", headers=headers).json()["total"] == 1
    assert client.get("/v1/runs?agent=booking", headers=headers).json()["total"] == 1


def test_graph_and_integration_diagnostics_are_truthful(client, project):
    headers = auth(project)
    now = datetime.now(timezone.utc)
    events = [
        event("otel-start", trace_id="otel-trace", event_type="run_started", kind="workflow", status="running", integration="opentelemetry", framework="deterministic-test", occurred_at=now.isoformat(), span_id="root"),
        event("otel-agent", trace_id="otel-trace", event_type="agent_span", kind="agent", integration="opentelemetry", framework="deterministic-test", occurred_at=(now + timedelta(milliseconds=1)).isoformat(), span_id="agent", parent_span_id="root", relationship="observed"),
        event("otel-handoff", trace_id="otel-trace", event_type="handoff", kind="handoff", integration="opentelemetry", framework="deterministic-test", occurred_at=(now + timedelta(milliseconds=2)).isoformat(), span_id="handoff", parent_span_id="agent", handoff_to="booking", relationship_confidence="unknown"),
    ]
    assert client.post("/v1/ingest/events", headers=headers, json={"events": events}).status_code == 200
    detail = client.get("/v1/runs/otel-trace", headers=headers).json()
    assert detail["graph"]["status"] == "partially_observed"
    assert detail["graph"]["summary"]["uncertain_relationship_count"] == 1
    assert detail["graph"]["summary"]["has_completion"] is False
    integrations = client.get("/v1/integrations", headers=headers).json()["items"]
    otel = next(item for item in integrations if item["id"] == "opentelemetry")
    callback = next(item for item in integrations if item["id"] == "callback")
    assert otel["state"] == "partially_observed"
    assert otel["events_received"] == 3
    assert callback["state"] == "no_events_received"


def test_failed_child_is_not_hidden_by_successful_workflow_completion(client, project):
    headers = auth(project)
    now = datetime.now(timezone.utc)
    events = [
        event("root-start", trace_id="failed-child", event_type="run_started", kind="workflow", status="running", span_id="root", occurred_at=now.isoformat()),
        event("child-failed", trace_id="failed-child", event_type="agent_span", kind="agent", status="failed", span_id="child", parent_span_id="root", occurred_at=(now + timedelta(milliseconds=1)).isoformat()),
        event("root-complete", trace_id="failed-child", event_type="run_completed", kind="workflow", status="succeeded", span_id="root", occurred_at=(now + timedelta(milliseconds=2)).isoformat()),
    ]
    assert client.post("/v1/ingest/events", headers=headers, json={"events": events}).status_code == 200
    run = client.get("/v1/runs/failed-child", headers=headers).json()
    assert run["status"] == "failed"
    assert run["graph"]["edges"][0]["from"] == "root-start"


def test_late_root_event_repairs_run_name_and_metadata(client, project):
    headers = auth(project)
    now = datetime.now(timezone.utc)
    events = [
        event("child-first", trace_id="late-root", event_type="agent_span", span_id="child", parent_span_id="root", metadata={"run_name": None}, occurred_at=now.isoformat()),
        event("root-late", trace_id="late-root", event_type="run_started", kind="workflow", status="running", span_id="root", metadata={"run_name": "late-root-workflow"}, occurred_at=(now + timedelta(milliseconds=1)).isoformat()),
    ]
    assert client.post("/v1/ingest/events", headers=headers, json={"events": events}).status_code == 200
    run = client.get("/v1/runs/late-root", headers=headers).json()
    assert run["name"] == "late-root-workflow"
    assert run["metadata"]["run_name"] == "late-root-workflow"
