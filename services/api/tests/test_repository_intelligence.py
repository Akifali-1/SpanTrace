from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import httpx

from app.main import settings
from app.repository import RepositoryImportError, fetch_public_github_archive


def zip_bytes(files: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def auth(project):
    return {"X-API-Key": project["api_key"]}


def test_zip_import_discovers_evidence_and_exports_configuration(client, project, tmp_path):
    marker = tmp_path / "executed-marker"
    fixture_secret = "fixture-" + "only-value-123"
    source = f'''import os
from pathlib import Path
from openai import OpenAI
from opentelemetry import trace

API_KEY = {fixture_secret!r}

class PlannerAgent:
    def plan(self, request):
        return request

def tool_search(query):
    return query

def booking_workflow(request):
    planner = PlannerAgent()
    planner.plan(request)
    client = OpenAI()
    client.responses.create(model="gpt-test", input=request)
    return tool_search(request)

if __name__ == "__main__":
    booking_workflow("Goa")

Path({str(marker)!r}).write_text("must never be created")
'''
    archive = zip_bytes({
        "fixture/workflow.py": source,
        "fixture/README.md": "Static fixture repository",
        "fixture/node_modules/ignored.js": "ignored generated dependency",
    })
    response = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("fixture.zip", archive, "application/zip")})
    assert response.status_code == 201, response.text
    body = response.json()
    analysis = body["analysis"]
    assert analysis["status"] == "analysis_complete"
    assert analysis["source_kind"] == "zip"
    assert analysis["summary"]["files_analyzed"] == 2
    kinds = {finding["kind"] for finding in analysis["findings"]}
    assert {"agent", "tool", "workflow_entry", "model_call"}.issubset(kinds)
    assert any(relationship["type"] == "invokes" for relationship in analysis["relationships"])
    assert not marker.exists(), "repository source must never be executed during analysis"

    entry = next(finding for finding in analysis["findings"] if finding["kind"] == "workflow_entry")
    component_ids = [finding["finding_id"] for finding in analysis["findings"] if finding["kind"] in {"agent", "tool", "model_call"}]
    config_response = client.post(
        f"/v1/repositories/{analysis['id']}/config",
        headers=auth(project),
        json={
            "schema_version": "1.0",
            "workflow_entry_point_ids": [entry["finding_id"]],
            "component_ids": component_ids,
            "adapter_ids": ["opentelemetry"],
            "capture_payloads": False,
            "redact_secrets": True,
        },
    )
    assert config_response.status_code == 201, config_response.text
    configuration = config_response.json()["configuration"]
    assert configuration["valid"] is True
    assert configuration["config"]["source"]["archive_fingerprint"] == analysis["archive_fingerprint"]
    assert fixture_secret not in str(configuration)

    exported = client.get(f"/v1/repositories/{analysis['id']}/config/export", headers=auth(project))
    assert exported.status_code == 200
    assert exported.json()["schema_version"] == "1.0"
    evidence = client.get(
        f"/v1/repositories/{analysis['id']}/source",
        headers=auth(project),
        params={"path": "fixture/workflow.py", "start_line": 6, "end_line": 6},
    )
    assert evidence.status_code == 200
    assert "[REDACTED]" in evidence.json()["lines"][0]["text"]


def test_zip_import_is_idempotent_and_rejects_zip_slip(client, project):
    archive = zip_bytes({"safe/workflow.py": "def main():\n    return True\n"})
    first = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("fixture.zip", archive, "application/zip")})
    second = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("fixture-again.zip", archive, "application/zip")})
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["reused"] is True
    assert client.get("/v1/repositories", headers=auth(project)).json()["items"]

    traversal = zip_bytes({"../../outside.py": "print('unsafe')"})
    rejected = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("unsafe.zip", traversal, "application/zip")})
    assert rejected.status_code == 400
    assert "traversal" in rejected.json()["detail"].lower()

    malformed = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("broken.zip", b"not a zip", "application/zip")})
    assert malformed.status_code == 400
    assert "valid zip" in malformed.json()["detail"].lower()

    symlink_buffer = BytesIO()
    with ZipFile(symlink_buffer, "w", ZIP_DEFLATED) as archive_file:
        info = ZipInfo("safe/link.py")
        info.create_system = 3
        info.external_attr = (0o120777 << 16) | 0xA0000000
        archive_file.writestr(info, "../../outside.py")
    symlink = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("symlink.zip", symlink_buffer.getvalue(), "application/zip")})
    assert symlink.status_code == 400
    assert "symlink" in symlink.json()["detail"].lower()


def test_repository_url_validation_is_read_only_and_project_scoped(client, project):
    invalid = client.post("/v1/repositories/import/url", headers=auth(project), json={"url": "http://169.254.169.254/latest/meta-data"})
    assert invalid.status_code == 400
    assert "github" in invalid.json()["detail"].lower()

    other = client.post("/v1/projects", json={"name": "Other repository project"}).json()
    archive = zip_bytes({"workflow.py": "def main():\n    pass\n"})
    imported = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("fixture.zip", archive, "application/zip")})
    analysis_id = imported.json()["analysis"]["id"]
    assert client.get(f"/v1/repositories/{analysis_id}", headers=auth(other)).status_code == 404


def test_configuration_validation_and_changed_revision_mark_old_configuration_stale(client, project):
    first = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("first.zip", zip_bytes({"workflow.py": "def main():\n    return 1\n"}), "application/zip")})
    first_analysis = first.json()["analysis"]
    invalid = client.post(
        f"/v1/repositories/{first_analysis['id']}/config",
        headers=auth(project),
        json={"workflow_entry_point_ids": ["st_missing"], "component_ids": [], "adapter_ids": []},
    )
    assert invalid.status_code == 422

    entry = next(finding for finding in first_analysis["findings"] if finding["kind"] == "workflow_entry")
    saved = client.post(
        f"/v1/repositories/{first_analysis['id']}/config",
        headers=auth(project),
        json={"workflow_entry_point_ids": [entry["finding_id"]], "component_ids": [], "adapter_ids": ["callback"]},
    )
    assert saved.status_code == 201

    second = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("second.zip", zip_bytes({"workflow.py": "def main():\n    return 2\n"}), "application/zip")})
    assert second.status_code == 201
    old = client.get(f"/v1/repositories/{first_analysis['id']}", headers=auth(project)).json()
    assert old["configuration"]["stale"] is True


def test_manifest_evidence_and_misleading_names_remain_conservative(client, project):
    archive = zip_bytes(
        {
            "pyproject.toml": '[project]\ndependencies = ["langgraph>=0.2", "openai>=1"]\n',
            "workflow.py": '\ufeff' + '''
class AgentFactory:
    def build(self):
        return object()

def toolbox(value):
    return value

def search_tool(value):
    return value

def model_step(value):
    from openai import OpenAI
    return OpenAI().responses.create(model="test", input=value)
''',
        }
    )
    response = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("fixture.zip", archive, "application/zip")})
    assert response.status_code == 201, response.text
    findings = response.json()["analysis"]["findings"]
    assert {item["name"] for item in findings if item["kind"] == "framework"} >= {"LangGraph", "OpenAI"}
    assert not any(item["kind"] == "agent" and item["name"] == "AgentFactory" for item in findings)
    assert not any(item["kind"] == "tool" and item["name"] == "toolbox" for item in findings)
    search = next(item for item in findings if item["name"] == "search_tool")
    assert search["confidence"] == "possible"
    model = next(item for item in findings if item["kind"] == "model_call")
    assert model["file_path"] == "workflow.py"
    assert model["start_line"] >= 10


def test_upload_limits_and_adapter_selection_are_enforced(client, project):
    original_limit = settings.repository_max_archive_bytes
    settings.repository_max_archive_bytes = 32
    try:
        oversized = client.post(
            "/v1/repositories/import/zip",
            headers=auth(project),
            files={"file": ("fixture.zip", zip_bytes({"workflow.py": "def main():\n    return True\n"}), "application/zip")},
        )
        assert oversized.status_code == 400
        assert "size" in oversized.json()["detail"].lower()
    finally:
        settings.repository_max_archive_bytes = original_limit

    archive = zip_bytes({"workflow.py": "def main():\n    return True\n"})
    imported = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("fixture.zip", archive, "application/zip")})
    analysis = imported.json()["analysis"]
    invalid_adapter = client.post(
        f"/v1/repositories/{analysis['id']}/config",
        headers=auth(project),
        json={"workflow_entry_point_ids": [], "component_ids": [], "adapter_ids": ["not-supported"]},
    )
    assert invalid_adapter.status_code == 422
    assert "adapter" in invalid_adapter.json()["detail"].lower()


def test_reanalysis_marks_existing_configuration_stale(client, project):
    archive = zip_bytes({"workflow.py": "def main():\n    return True\n"})
    imported = client.post("/v1/repositories/import/zip", headers=auth(project), files={"file": ("fixture.zip", archive, "application/zip")})
    analysis = imported.json()["analysis"]
    entry = next(item for item in analysis["findings"] if item["kind"] == "workflow_entry")
    saved = client.post(
        f"/v1/repositories/{analysis['id']}/config",
        headers=auth(project),
        json={"workflow_entry_point_ids": [entry["finding_id"]], "component_ids": [], "adapter_ids": ["callback"]},
    )
    assert saved.status_code == 201
    refreshed = client.post(f"/v1/repositories/{analysis['id']}/reanalyze", headers=auth(project))
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["analysis"]["configuration"]["stale"] is True


def test_public_github_fetch_resolves_revision_without_following_redirects(monkeypatch):
    class Response:
        def __init__(self, status_code, payload=None, chunks=None):
            self.status_code = status_code
            self._payload = payload
            self._chunks = chunks or []

        def json(self):
            return self._payload

        def iter_bytes(self, _chunk_size):
            return iter(self._chunks)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url):
            if url.endswith("/commits/main"):
                return Response(200, {"sha": "a" * 40})
            return Response(200, {"full_name": "acme/support", "private": False, "default_branch": "main"})

        def stream(self, _method, _url):
            return Response(200, chunks=[b"PK", b"\x03\x04"])

    monkeypatch.setattr("app.repository.httpx.Client", Client)
    archive, metadata = fetch_public_github_archive("https://github.com/acme/support", None, settings)
    assert archive == b"PK\x03\x04"
    assert metadata["branch"] == "main"
    assert metadata["commit_sha"] == "a" * 40


def test_public_github_timeout_is_actionable(monkeypatch):
    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, _url):
            raise httpx.ReadTimeout("upstream timeout")

    monkeypatch.setattr("app.repository.httpx.Client", Client)
    try:
        fetch_public_github_archive("https://github.com/acme/support", "main", settings)
    except RepositoryImportError as error:
        assert "timed out" in str(error).lower()
    else:
        raise AssertionError("GitHub timeouts must be converted into an actionable import error")
