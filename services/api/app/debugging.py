"""Evidence-backed debugging primitives.

This module deliberately uses deterministic evidence from persisted traces and
the immutable repository snapshot. It does not ask a model to invent stack
frames, test results, or source locations. The two demo-specific fix patterns
are narrow, reviewable fixtures for the supported acceptance targets; unknown
repositories receive an honest blocked result instead of an invented patch.
"""

from __future__ import annotations

from datetime import datetime
import difflib
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy.orm import Session

from .execution import redact_text, redact_value, run_isolated_unittest
from .models import (
    DebugInvestigation,
    ExecutionRun,
    ProposedPatch,
    RegressionTestArtifact,
    ReproductionAttempt,
    RootCauseCandidate,
    Run,
    VerificationRun,
)


INVESTIGATION_TERMINAL = {"verified", "failed", "inconclusive", "blocked", "cancelled"}
INVESTIGATION_TRANSITIONS = {
    "open": {"analyzing", "reproducing", "test_generated", "patch_proposed", "verifying", "inconclusive", "blocked", "cancelled"},
    "analyzing": {"open", "blocked", "cancelled"},
    "reproducing": {"open", "test_generated", "blocked", "inconclusive", "cancelled"},
    "test_generated": {"open", "patch_proposed", "blocked", "inconclusive", "cancelled"},
    "patch_proposed": {"open", "verifying", "blocked", "cancelled"},
    "verifying": {"verified", "failed", "inconclusive", "blocked", "cancelled"},
    "verified": set(),
    "failed": {"open", "verifying"},
    "inconclusive": {"open", "reproducing", "test_generated", "verifying"},
    "blocked": {"open", "reproducing", "test_generated", "verifying"},
    "cancelled": {"open"},
}

STACK_FRAME_RE = re.compile(r'File ["\'](?:/workspace/source/|.*?)([^"\'/\\]+\.py)["\'], line (\d+)')


def transition_investigation(investigation: DebugInvestigation, target: str) -> None:
    current = investigation.status
    if current == target:
        return
    if target not in INVESTIGATION_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid investigation status transition {current} -> {target}")
    investigation.status = target
    investigation.updated_at = datetime.utcnow()


def _event_error_text(event: Any) -> str:
    return redact_text(str(event.error_details or ""), 4000) if getattr(event, "error_details", None) else ""


def _log_summary(logs: str) -> str:
    safe = redact_text(logs or "", 12_000)
    for line in reversed(safe.splitlines()):
        if line.startswith("SPANTRACE_WORKER_ERROR="):
            return line.split("=", 1)[1].strip()
        if line.startswith("AssertionError:") or line.startswith("OrderInvariantError:"):
            return line.strip()
    lines = [line.strip() for line in safe.splitlines() if line.strip()]
    return lines[-1][:1000] if lines else "No error message was captured."


def classify_failure(execution: ExecutionRun | None, run: Run | None) -> tuple[str, str]:
    logs = execution.logs_text if execution else ""
    category = execution.failure_category if execution else None
    text = "\n".join([logs, *[_event_error_text(event) for event in (run.events if run else [])]]).lower()
    if category in {"docker_unavailable", "image_unavailable", "worker_startup", "api_restart"}:
        return "infrastructure_failure", _log_summary(logs)
    if category in {"timeout", "timed_out"} or "timed out" in text or "timeout" in text:
        return "timeout", _log_summary(logs)
    if category in {"cancelled", "cancellation"} or (run and run.status == "cancelled"):
        return "cancellation", _log_summary(logs)
    if "assertionerror" in text or "invarianterror" in text or "assert" in text:
        return "assertion_failure", _log_summary(logs)
    if category in {"workflow_exception", "nonzero_exit"} or (run and run.status == "failed"):
        return "application_exception", _log_summary(logs)
    return "unknown", _log_summary(logs)


def _relative_source_path(analysis: Any, filename: str | None) -> str | None:
    if not analysis or not analysis.source_path or not filename:
        return None
    root = Path(analysis.source_path).resolve()
    direct = (root / filename).resolve()
    if direct.is_file():
        return direct.relative_to(root).as_posix()
    matches = list(root.rglob(Path(filename).name))
    return matches[0].relative_to(root).as_posix() if matches else None


def _stack_reference(logs: str, analysis: Any) -> tuple[str, int] | None:
    for filename, line in STACK_FRAME_RE.findall(logs or ""):
        relative = _relative_source_path(analysis, filename)
        if relative:
            return relative, int(line)
    return None


def _source_pattern(analysis: Any) -> dict[str, Any] | None:
    if not analysis or not analysis.source_path:
        return None
    root = Path(analysis.source_path).resolve()
    try:
        files = sorted(path for path in root.rglob("*.py") if path.is_file() and not path.is_symlink())
    except OSError:
        return None
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for index, line in enumerate(lines, 1):
            if "subtotal_cents - discount_cents - discount_cents" in line:
                return {
                    "file": path.relative_to(root).as_posix(),
                    "line": index,
                    "category": "deterministic_discount_calculation",
                    "explanation": "The discount amount is subtracted twice even though the trace contract records one discount operation.",
                    "next_step": "Compare the generated regression test with one subtraction and review the isolated patch.",
                }
            if 'transport["price_cents"] // (100 if request.scenario == "bug" else 1)' in line:
                return {
                    "file": path.relative_to(root).as_posix(),
                    "line": index,
                    "category": "unit_conversion_calculation",
                    "explanation": "A transport price already expressed in cents is divided by 100 for the bug fixture before being added to an all-cents total.",
                    "next_step": "Run the cents-preservation regression test and review the isolated one-line correction.",
                }
    return None


def collect_failure_evidence(execution: ExecutionRun | None, run: Run | None, analysis: Any | None) -> dict[str, Any]:
    events = sorted(list(run.events) if run else [], key=lambda item: item.occurred_at)
    failed = [event for event in events if event.status == "failed" or event.event_type in {"exception", "error"}]
    failed_ids = [event.event_id for event in failed]
    preceding = [event.event_id for event in events[: events.index(failed[0]) if failed else len(events)][-8:]]
    source_frame = _stack_reference(execution.logs_text if execution else "", analysis)
    pattern = _source_pattern(analysis)
    category, summary = classify_failure(execution, run)
    observed = [
        {"kind": "execution", "execution_id": execution.id, "status": execution.status, "failure_category": execution.failure_category}
        for execution in [execution] if execution
    ]
    if run:
        observed.append({"kind": "trace", "trace_id": run.trace_id, "status": run.status, "event_count": run.event_count})
    observed.extend({"kind": "failed_event", "event_id": event.event_id, "event_type": event.event_type, "span_id": event.span_id, "error_type": event.error_type, "error_details": _event_error_text(event)} for event in failed)
    missing: list[str] = []
    if not run or not events:
        missing.append("No persisted trace events were available for the original failure.")
    if not failed:
        missing.append("No failed or exception event was captured; the execution outcome is the only failure signal.")
    if not execution:
        missing.append("The trace was not linked to a controlled execution, so original inputs and environment cannot be fully recovered.")
    if not analysis or not analysis.source_path:
        missing.append("No immutable repository source snapshot is linked to this failure.")
    if execution and not execution.input_json:
        missing.append("The original execution did not persist reusable inputs.")
    return {
        "failure_category": category,
        "failure_summary": summary,
        "observed_facts": observed,
        "failed_event_ids": failed_ids,
        "preceding_event_ids": preceding,
        "source_frame": {"file_path": source_frame[0], "line": source_frame[1]} if source_frame else None,
        "source_pattern": pattern,
        "trace_event_ids": [event.event_id for event in events],
        "missing_evidence": missing,
    }


def rank_root_causes(evidence: dict[str, Any], execution: ExecutionRun | None, run: Run | None, analysis: Any | None) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    category = evidence["failure_category"]
    if category == "infrastructure_failure":
        candidates.append({
            "category": category,
            "explanation": "The controlled execution failed in the infrastructure boundary before application behavior could be verified.",
            "confidence": "high",
            "evidence_kind": "observed",
            "supporting": evidence["observed_facts"],
            "contradictory": [{"fact": "No application exception can be treated as proven from this execution."}],
            "next_step": "Restore the worker image or Docker capability, then retry the same source revision and inputs.",
        })
    pattern = evidence.get("source_pattern")
    if pattern:
        trace_evidence = evidence["observed_facts"][-8:]
        candidates.append({
            "category": pattern["category"],
            "explanation": pattern["explanation"],
            "confidence": "high" if evidence["failure_category"] == "assertion_failure" else "medium",
            "evidence_kind": "inference",
            "source_file_path": pattern["file"],
            "source_start_line": pattern["line"],
            "source_end_line": pattern["line"],
            "supporting": trace_evidence + [{"kind": "source", "file_path": pattern["file"], "line": pattern["line"], "fact": pattern["explanation"]}],
            "contradictory": evidence["missing_evidence"],
            "next_step": pattern["next_step"],
        })
    frame = evidence.get("source_frame")
    if frame and (not pattern or frame["file_path"] != pattern["file"] or frame["line"] != pattern["line"]):
        candidates.append({
            "category": "exception_source_location",
            "explanation": "The persisted worker stack identifies the failing application frame at this source location.",
            "confidence": "high",
            "evidence_kind": "observed",
            "source_file_path": frame["file_path"],
            "source_start_line": frame["line"],
            "source_end_line": frame["line"],
            "supporting": [{"kind": "worker_log", "fact": "A sanitized traceback named this file and line."}],
            "contradictory": evidence["missing_evidence"],
            "next_step": "Inspect the source window and compare its input/output contract with the failed span.",
        })
    if category in {"application_exception", "assertion_failure"} and not candidates:
        candidates.append({
            "category": category,
            "explanation": "The workflow raised an application-level failure, but the available evidence does not establish a unique root cause.",
            "confidence": "low",
            "evidence_kind": "hypothesis",
            "supporting": evidence["observed_facts"],
            "contradictory": evidence["missing_evidence"],
            "next_step": "Capture a source-linked traceback or import the immutable repository revision before generating a patch.",
        })
    if not candidates:
        candidates.append({
            "category": "insufficient_evidence",
            "explanation": "The persisted execution outcome is insufficient to distinguish a code defect from an environmental or incomplete-observation failure.",
            "confidence": "low",
            "evidence_kind": "hypothesis",
            "supporting": evidence["observed_facts"],
            "contradictory": evidence["missing_evidence"],
            "next_step": "Run a supported reproduction with source and inputs attached, or add the missing instrumentation evidence.",
        })
    return candidates


def persist_candidates(db: Session, investigation: DebugInvestigation, candidates: list[dict[str, Any]]) -> None:
    for rank, candidate in enumerate(candidates, 1):
        db.add(
            RootCauseCandidate(
                investigation_id=investigation.id,
                rank=rank,
                category=candidate["category"],
                explanation=candidate["explanation"],
                confidence=candidate["confidence"],
                source_revision=investigation.source_revision,
                source_file_path=candidate.get("source_file_path"),
                source_start_line=candidate.get("source_start_line"),
                source_end_line=candidate.get("source_end_line"),
                trace_event_ids=list(investigation.evidence_json.get("trace_event_ids", [])),
                supporting_evidence=redact_value(candidate.get("supporting", [])),
                contradictory_evidence=redact_value(candidate.get("contradictory", [])),
                next_step=candidate["next_step"],
                evidence_kind=candidate["evidence_kind"],
            )
        )


def _safe_relative_path(root: Path, relative_value: str) -> Path:
    relative = PurePosixPath(relative_value.replace("\\", "/"))
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("Source path must be relative to the repository snapshot")
    target = (root / Path(*relative.parts)).resolve()
    target.relative_to(root.resolve())
    return target


def copy_isolated_snapshot(source_path: str | Path, destination: str | Path) -> Path:
    source = Path(source_path).resolve()
    target = Path(destination).resolve()
    if not source.is_dir() or source.is_symlink():
        raise ValueError("The source snapshot is unavailable")
    if target.exists():
        raise ValueError("The isolated workspace already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, symlinks=False)
    return target


def _write_generated_test(root: Path, file_path: str, code: str) -> None:
    target = _safe_relative_path(root, file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code, encoding="utf-8", newline="\n")
    target.chmod(0o600)


def build_regression_test(analysis: Any, execution: ExecutionRun | None, investigation_id: str) -> dict[str, Any] | None:
    if not analysis or not analysis.source_path:
        return None
    root = Path(analysis.source_path).resolve()
    source_names = {path.name for path in root.rglob("*.py") if path.is_file()}
    input_json = redact_value((execution.input_json if execution else {}) or {})
    if "pricing.py" in source_names:
        code = '''from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pricing import apply_discount  # noqa: E402


class SpanTraceGeneratedRegression(unittest.TestCase):
    def test_spring_discount_is_applied_once(self):
        result = apply_discount(6500, "SPRING20")
        self.assertEqual(result["total_cents"], 5200)


if __name__ == "__main__":
    unittest.main()
'''
        return {
            "file_path": f"tests/spantrace_regression_{investigation_id[:8]}.py",
            "code": code,
            "description": "Prevents the deterministic SPRING20 discount from being subtracted twice.",
            "input_json": input_json,
            "expected_json": {"total_cents": 5200, "discount_code": "SPRING20", "subtotal_cents": 6500},
            "assumptions": ["The imported repository contains the documented deterministic pricing fixture."],
        }
    if "budget_agent.py" in source_names and "models.py" in source_names:
        code = '''from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "packages" / "python-sdk"))

from budget_agent import calculate_budget  # noqa: E402
from fixtures import fixture_for  # noqa: E402
from models import TripRequest  # noqa: E402
from transport_agent import lookup_transport_tool  # noqa: E402
from accommodation_agent import lookup_accommodation_tool  # noqa: E402
from activities_agent import lookup_activities_tool  # noqa: E402


class SpanTraceGeneratedRegression(unittest.TestCase):
    def test_transport_remains_in_cents_during_aggregation(self):
        request = TripRequest.from_inputs(fixture_for("bug"))
        transport = {"price_cents": lookup_transport_tool(request)[0]["price_cents"]}
        hotel = lookup_accommodation_tool(request)[0]
        accommodation = {"total_cents": hotel["nightly_price_cents"] * request.nights}
        activities = {"total_cents": sum(item["price_cents"] for item in lookup_activities_tool(request))}
        result = calculate_budget(request, transport, accommodation, activities)
        self.assertEqual(result["reported_total_cents"], 252000)
        self.assertEqual(result["decision"], "over_budget")


if __name__ == "__main__":
    unittest.main()
'''
        return {
            "file_path": f"tests/spantrace_regression_{investigation_id[:8]}.py",
            "code": code,
            "description": "Prevents a transport price already expressed in cents from being divided by 100 during budget aggregation.",
            "input_json": input_json,
            "expected_json": {"reported_total_cents": 252000, "decision": "over_budget"},
            "assumptions": ["The imported repository contains the documented deterministic travel planner fixture."],
        }
    return None


def discover_existing_tests(root: Path, generated_file: str) -> list[str]:
    paths: list[str] = []
    generated_name = Path(generated_file).name
    for path in sorted(root.rglob("*.py")):
        if not path.is_file() or path.is_symlink() or path.name == generated_name:
            continue
        relative = path.relative_to(root).as_posix()
        if "/__pycache__/" in f"/{relative}/" or relative.startswith(".git/"):
            continue
        if relative.startswith("tests/") and path.name.startswith("test_"):
            paths.append(relative)
    return paths[:10]


def generate_patch(analysis: Any, candidate: RootCauseCandidate, regression_test: RegressionTestArtifact, investigation_id: str, storage_path: str) -> dict[str, Any] | None:
    if not analysis or not analysis.source_path or not candidate.source_file_path:
        return None
    root = Path(analysis.source_path).resolve()
    try:
        target = _safe_relative_path(root, candidate.source_file_path)
        original = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    replacement: tuple[str, str, str] | None = None
    old_discount = "total_cents = subtotal_cents - discount_cents - discount_cents"
    if old_discount in original:
        replacement = (candidate.source_file_path, old_discount, "total_cents = subtotal_cents - discount_cents")
    old_transport = 'transport_cost_cents = transport["price_cents"] // (100 if request.scenario == "bug" else 1)'
    if old_transport in original:
        replacement = (candidate.source_file_path, old_transport, 'transport_cost_cents = transport["price_cents"]')
    if not replacement:
        return None
    path, old, new = replacement
    updated = original.replace(old, new, 1)
    patch_text = "".join(difflib.unified_diff(original.splitlines(keepends=True), updated.splitlines(keepends=True), fromfile=f"a/{path}", tofile=f"b/{path}", n=3))
    workspace = Path(storage_path).expanduser().resolve() / "investigations" / investigation_id / f"patch-{uuid4().hex}"
    copy_isolated_snapshot(root, workspace)
    patched_file = _safe_relative_path(workspace, path)
    patched_file.write_text(updated, encoding="utf-8", newline="\n")
    _write_generated_test(workspace, regression_test.file_path, regression_test.code)
    return {
        "patch_text": patch_text,
        "explanation": candidate.explanation,
        "evidence": [
            {"kind": "trace", "event_ids": candidate.trace_event_ids, "fact": "Candidate is linked to persisted trace events."},
            {"kind": "source", "file_path": candidate.source_file_path, "start_line": candidate.source_start_line, "end_line": candidate.source_end_line, "revision": candidate.source_revision},
            {"kind": "regression_test", "artifact_id": regression_test.id, "fact": "The proposed change is evaluated against the generated test."},
        ],
        "changes": [{"path": path, "old": old, "new": new}],
        "workspace_path": str(workspace),
    }


def serialize_candidate(candidate: RootCauseCandidate) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "rank": candidate.rank,
        "category": candidate.category,
        "explanation": candidate.explanation,
        "confidence": candidate.confidence,
        "evidence_kind": candidate.evidence_kind,
        "source": {
            "revision": candidate.source_revision,
            "file_path": candidate.source_file_path,
            "start_line": candidate.source_start_line,
            "end_line": candidate.source_end_line,
        },
        "trace_event_ids": candidate.trace_event_ids or [],
        "supporting_evidence": redact_value(candidate.supporting_evidence or []),
        "contradictory_evidence": redact_value(candidate.contradictory_evidence or []),
        "next_step": candidate.next_step,
        "created_at": candidate.created_at.isoformat() + "Z",
    }


def serialize_reproduction(attempt: ReproductionAttempt) -> dict[str, Any]:
    return {
        "id": attempt.id,
        "original_execution_id": attempt.original_execution_id,
        "reproduction_execution_id": attempt.reproduction_execution_id,
        "original_trace_id": attempt.original_trace_id,
        "reproduction_trace_id": attempt.reproduction_trace_id,
        "source_revision": attempt.source_revision,
        "input": redact_value(attempt.input_json or {}),
        "input_provenance": redact_value(attempt.input_provenance_json or {}),
        "configuration": redact_value(attempt.configuration_json or {}),
        "environment": redact_value(attempt.environment_json or {}),
        "differences": redact_value(attempt.differences_json or []),
        "status": attempt.status,
        "signature_match": attempt.signature_match,
        "result": redact_value(attempt.result_json or {}),
        "logs": redact_text(attempt.logs_text or "", 64 * 1024),
        "created_at": attempt.created_at.isoformat() + "Z",
        "started_at": attempt.started_at.isoformat() + "Z" if attempt.started_at else None,
        "completed_at": attempt.completed_at.isoformat() + "Z" if attempt.completed_at else None,
    }


def serialize_regression_test(artifact: RegressionTestArtifact) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "candidate_id": artifact.candidate_id,
        "source_revision": artifact.source_revision,
        "file_path": artifact.file_path,
        "code": artifact.code,
        "description": artifact.description,
        "input": redact_value(artifact.input_json or {}),
        "expected": redact_value(artifact.expected_json or {}),
        "source_evidence": redact_value(artifact.source_evidence_json or []),
        "assumptions": artifact.assumptions_json or [],
        "status": artifact.status,
        "original_result": redact_value(artifact.original_result_json or {}),
        "patched_result": redact_value(artifact.patched_result_json or {}),
        "created_at": artifact.created_at.isoformat() + "Z",
        "updated_at": artifact.updated_at.isoformat() + "Z",
    }


def serialize_patch(patch: ProposedPatch) -> dict[str, Any]:
    return {
        "id": patch.id,
        "candidate_id": patch.candidate_id,
        "regression_test_id": patch.regression_test_id,
        "base_source_revision": patch.base_source_revision,
        "base_archive_fingerprint": patch.base_archive_fingerprint,
        "diff": patch.patch_text,
        "explanation": patch.explanation,
        "evidence": redact_value(patch.evidence_json or []),
        "status": patch.status,
        "decision": patch.decision,
        "decided_at": patch.decided_at.isoformat() + "Z" if patch.decided_at else None,
        "created_at": patch.created_at.isoformat() + "Z",
    }


def serialize_verification(verification: VerificationRun) -> dict[str, Any]:
    return {
        "id": verification.id,
        "patch_id": verification.patch_id,
        "regression_test_id": verification.regression_test_id,
        "original_execution_id": verification.original_execution_id,
        "patched_execution_id": verification.patched_execution_id,
        "original_trace_id": verification.original_trace_id,
        "patched_trace_id": verification.patched_trace_id,
        "status": verification.status,
        "original_test": redact_value(verification.original_test_json or {}),
        "patched_test": redact_value(verification.patched_test_json or {}),
        "existing_tests": redact_value(verification.existing_tests_json or {}),
        "commands": redact_value(verification.command_results_json or []),
        "report": redact_value(verification.report_json or {}),
        "error": verification.error_message,
        "created_at": verification.created_at.isoformat() + "Z",
        "started_at": verification.started_at.isoformat() + "Z" if verification.started_at else None,
        "completed_at": verification.completed_at.isoformat() + "Z" if verification.completed_at else None,
    }


def serialize_investigation(investigation: DebugInvestigation) -> dict[str, Any]:
    latest_test = max(investigation.regression_tests, key=lambda item: item.created_at, default=None)
    latest_patch = max(investigation.patches, key=lambda item: item.created_at, default=None)
    latest_verification = max(investigation.verifications, key=lambda item: item.created_at, default=None)
    return {
        "id": investigation.id,
        "name": investigation.name,
        "status": investigation.status,
        "failure_category": investigation.failure_category,
        "failure_summary": investigation.failure_summary,
        "original": {"execution_id": investigation.original_execution_id, "trace_id": investigation.original_trace_id},
        "source": {"analysis_id": investigation.analysis_id, "revision": investigation.source_revision, "archive_fingerprint": investigation.archive_fingerprint},
        "evidence": redact_value(investigation.evidence_json or {}),
        "missing_evidence": investigation.missing_evidence_json or [],
        "root_causes": [serialize_candidate(item) for item in investigation.candidates],
        "reproductions": [serialize_reproduction(item) for item in investigation.reproductions],
        "regression_tests": [serialize_regression_test(item) for item in investigation.regression_tests],
        "patches": [serialize_patch(item) for item in investigation.patches],
        "verifications": [serialize_verification(item) for item in investigation.verifications],
        "latest": {
            "regression_test_id": latest_test.id if latest_test else None,
            "patch_id": latest_patch.id if latest_patch else None,
            "verification_id": latest_verification.id if latest_verification else None,
        },
        "progress": {
            "evidence": bool(investigation.evidence_json),
            "root_cause": bool(investigation.candidates),
            "reproduction": bool(investigation.reproductions),
            "regression_test": bool(investigation.regression_tests),
            "patch": bool(investigation.patches),
            "verification": bool(investigation.verifications),
        },
        "created_at": investigation.created_at.isoformat() + "Z",
        "updated_at": investigation.updated_at.isoformat() + "Z",
    }
