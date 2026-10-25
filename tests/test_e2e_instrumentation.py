from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from examples.travel_booking.main import run_otel


def _request(url: str, *, method: str = "GET", body: dict | None = None, api_key: str | None = None) -> dict:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if payload else {}
    if api_key:
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(url, data=payload, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_real_otel_example_reaches_running_api_without_mocking_ingestion(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    port = _free_port()
    database_path = (tmp_path / "spantrace-e2e.db").resolve()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(repo_root / "services" / "api"), str(repo_root / "packages" / "python-sdk")])
    env["SPANTRACE_DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    env["SPANTRACE_CORS_ORIGINS"] = "http://127.0.0.1"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=repo_root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                if _request(f"{base_url}/health")["status"] == "ok":
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("The isolated SpanTrace API did not start.")

        project = _request(f"{base_url}/v1/projects", method="POST", body={"name": "E2E project"})
        api_key = project["api_key"]
        project_id = project["project"]["id"]
        trace_id = run_otel("failure", api_key=api_key, api_url=base_url, project_id=project_id)
        run = _request(f"{base_url}/v1/runs/{trace_id}", api_key=api_key)

        assert run["name"] == "travel-booking"
        assert run["status"] == "failed"
        assert run["event_count"] >= 15
        assert {event["integration"] for event in run["events"]} == {"opentelemetry"}
        assert run["graph"]["summary"]["has_root"] is True
        assert run["graph"]["summary"]["has_completion"] is True
        assert run["incidents"][0]["responsible_span_id"]
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
