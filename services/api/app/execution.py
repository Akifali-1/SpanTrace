"""Durable control-plane supervision for the narrow Docker execution MVP.

The API process only launches and supervises Docker. Imported source is loaded
and executed by ``spantrace-worker`` inside the container, never in this
module or the FastAPI process.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .models import ExecutionRun


TERMINAL_STATUSES = {"succeeded", "failed", "timed_out", "cancelled", "infrastructure_error"}
ACTIVE_STATUSES = {"queued", "starting", "running", "cancel_requested"}
SECRET_TEXT_RE = re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|authorization|password|secret)\s*([:=])\s*(?:\"[^\"\n]*\"|'[^'\n]*'|[^\s,;]+)")


def execution_token() -> str:
    return f"sexec_{uuid4().hex}{uuid4().hex}"


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def input_fingerprint(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        sensitive = {"password", "passwd", "secret", "token", "api_key", "apikey", "authorization", "client_secret", "access_token", "refresh_token"}
        return {key: "[REDACTED]" if str(key).lower() in sensitive else redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return SECRET_TEXT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value)
    return value


def redact_text(value: str, max_bytes: int) -> str:
    redacted = SECRET_TEXT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value)
    encoded = redacted.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return redacted
    return encoded[:max_bytes].decode("utf-8", errors="ignore") + "\n[log output truncated]"


def transition_status(execution: ExecutionRun, target: str) -> None:
    current = execution.status
    if current in TERMINAL_STATUSES:
        if current != target:
            raise ValueError(f"Terminal execution status {current} cannot transition to {target}")
        return
    allowed = {
        "queued": {"starting", "cancel_requested", "infrastructure_error"},
        "starting": {"running", "cancel_requested", "failed", "infrastructure_error"},
        "running": {"succeeded", "failed", "timed_out", "cancel_requested", "infrastructure_error"},
        "cancel_requested": {"cancelled", "failed", "timed_out", "infrastructure_error"},
    }
    if target not in allowed.get(current, set()):
        raise ValueError(f"Invalid execution status transition {current} -> {target}")
    execution.status = target


def serialize_execution(execution: ExecutionRun, *, include_logs: bool = True) -> dict[str, Any]:
    result = {
        "id": execution.id,
        "analysis_id": execution.analysis_id,
        "configuration_id": execution.configuration_id,
        "source_revision": execution.source_revision,
        "archive_fingerprint": execution.archive_fingerprint,
        "workflow_entry_point_id": execution.entry_finding_id,
        "entry_file_path": execution.entry_file_path,
        "entry_symbol": execution.entry_symbol,
        "trace_id": execution.trace_id,
        "status": execution.status,
        "input": redact_value(execution.input_json or {}),
        "worker_container_id": execution.worker_container_id,
        "exit_code": execution.exit_code,
        "failure_category": execution.failure_category,
        "result": redact_value(execution.result_json or {}),
        "timeout_seconds": execution.timeout_seconds,
        "memory_mb": execution.memory_mb,
        "cpu_limit": execution.cpu_limit,
        "pids_limit": execution.pids_limit,
        "created_at": execution.created_at.isoformat() + "Z",
        "started_at": execution.started_at.isoformat() + "Z" if execution.started_at else None,
        "completed_at": execution.completed_at.isoformat() + "Z" if execution.completed_at else None,
        "cancel_requested_at": execution.cancel_requested_at.isoformat() + "Z" if execution.cancel_requested_at else None,
    }
    if include_logs:
        result["logs"] = redact_text(execution.logs_text or "", 256 * 1024)
    return result


class ExecutionCoordinator:
    def __init__(self, settings: Settings, session_factory: sessionmaker[Session]) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="spantrace-worker")
        self._futures: dict[str, Future[Any]] = {}
        self._tokens: dict[str, str] = {}
        self._inputs: dict[str, dict[str, Any]] = {}
        self._processes: dict[str, tuple[subprocess.Popen[str], str]] = {}
        self._lock = threading.RLock()

    def reconcile(self) -> None:
        """Mark runs owned by a previous API process as recoverable failures."""
        db = self.session_factory()
        try:
            stale = db.query(ExecutionRun).filter(ExecutionRun.status.in_(ACTIVE_STATUSES)).all()
            for execution in stale:
                if execution.worker_container_id:
                    self._kill_container(execution.worker_container_id)
                execution.status = "infrastructure_error"
                execution.failure_category = "api_restart"
                execution.completed_at = datetime.utcnow()
                execution.logs_text = "Execution was interrupted because the control plane restarted before completion. Retry the run."
            db.commit()
        finally:
            db.close()

    def submit(self, execution_id: str, raw_token: str, inputs: dict[str, Any]) -> None:
        with self._lock:
            self._tokens[execution_id] = raw_token
            self._inputs[execution_id] = inputs
            self._futures[execution_id] = self.executor.submit(self._run, execution_id)

    def request_cancel(self, execution_id: str) -> bool:
        db = self.session_factory()
        try:
            execution = db.get(ExecutionRun, execution_id)
            if not execution or execution.status in TERMINAL_STATUSES:
                return False
            if execution.status != "cancel_requested":
                transition_status(execution, "cancel_requested")
            execution.cancel_requested_at = datetime.utcnow()
            db.commit()
            with self._lock:
                process_info = self._processes.get(execution_id)
            if process_info:
                self._kill_container(process_info[1])
            return True
        finally:
            db.close()

    def shutdown(self) -> None:
        with self._lock:
            ids = list(self._processes)
        for execution_id in ids:
            with self._lock:
                process_info = self._processes.get(execution_id)
            if process_info:
                self._kill_container(process_info[1])
        self.executor.shutdown(wait=False, cancel_futures=False)

    def _set_status(self, execution_id: str, target: str, *, failure_category: str | None = None, exit_code: int | None = None, logs: str | None = None, result: dict[str, Any] | None = None) -> None:
        db = self.session_factory()
        try:
            execution = db.get(ExecutionRun, execution_id)
            if not execution:
                return
            if execution.status != target:
                try:
                    transition_status(execution, target)
                except ValueError:
                    return
            if target == "running" and execution.started_at is None:
                execution.started_at = datetime.utcnow()
            if target in TERMINAL_STATUSES:
                execution.completed_at = execution.completed_at or datetime.utcnow()
            if failure_category:
                execution.failure_category = failure_category
            if exit_code is not None:
                execution.exit_code = exit_code
            if logs is not None:
                execution.logs_text = redact_text(logs, self.settings.execution_log_bytes)
            if result is not None:
                execution.result_json = redact_value(result)
            db.commit()
        finally:
            db.close()

    def _run(self, execution_id: str) -> None:
        db = self.session_factory()
        try:
            execution = db.get(ExecutionRun, execution_id)
            if not execution:
                return
            analysis = execution.analysis
            configuration = execution.configuration
            if execution.status == "cancel_requested":
                self._set_status(execution_id, "cancelled", failure_category="cancelled")
                return
            transition_status(execution, "starting")
            db.commit()
            if shutil.which("docker") is None:
                self._set_status(execution_id, "infrastructure_error", failure_category="docker_unavailable", logs="Docker CLI is not available to the SpanTrace API process.")
                return
            image_check = subprocess.run(["docker", "image", "inspect", self.settings.execution_worker_image], capture_output=True, text=True, timeout=15, check=False)
            if image_check.returncode != 0:
                self._set_status(execution_id, "infrastructure_error", failure_category="image_unavailable", logs=f"Worker image {self.settings.execution_worker_image} is unavailable. Build it with: docker build -f services/worker/Dockerfile -t {self.settings.execution_worker_image} .")
                return
            source_root = Path(analysis.source_path or "").resolve()
            storage_root = Path(self.settings.repository_storage_path).expanduser().resolve()
            source_root.relative_to(storage_root)
            entry_path = PurePosixPath(execution.entry_file_path)
            if not entry_path.parts or any(part in {"", ".", ".."} for part in entry_path.parts) or entry_path.suffix != ".py":
                raise ValueError("Execution entry point must be a relative Python source path")
            entry_file = source_root.joinpath(*entry_path.parts).resolve()
            entry_file.relative_to(source_root)
            if not entry_file.is_file():
                raise ValueError("Execution source entry point is no longer available")
            adapters = [str(item.get("id")) for item in (configuration.config_json or {}).get("adapters", []) if isinstance(item, dict)]
            adapter = "opentelemetry" if "opentelemetry" in adapters else "callback" if "callback" in adapters else "manual"
            capture_payloads = bool((configuration.config_json or {}).get("instrumentation", {}).get("capture_payloads", False))
            container = f"spantrace-exec-{execution.id[:12]}"
            with self._lock:
                token = self._tokens.get(execution.id)
            if not token:
                raise RuntimeError("Execution capability was not available to the worker coordinator")
            with self._lock:
                input_value = self._inputs.get(execution.id, execution.input_json or {})
            input_json = json.dumps(input_value, separators=(",", ":"), default=str)
            command = [
                "docker", "run", "--rm", "--name", container,
                "--user", "1000:1000", "--read-only", "--cap-drop=ALL",
                "--security-opt=no-new-privileges", f"--pids-limit={execution.pids_limit}",
                f"--memory={execution.memory_mb}m", f"--cpus={execution.cpu_limit}",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
                "--mount", f"type=bind,source={source_root},target=/workspace/source,readonly",
                "--add-host", "host.docker.internal:host-gateway",
                "--env", f"SPANTRACE_API_URL={self.settings.execution_worker_api_url}",
                "--env", f"SPANTRACE_EXECUTION_TOKEN={token}",
                "--env", f"SPANTRACE_EXECUTION_ID={execution.id}",
                "--env", f"SPANTRACE_TRACE_ID={execution.trace_id}",
                "--env", f"SPANTRACE_PROJECT_ID={execution.project_id}",
                "--env", f"SPANTRACE_EXECUTION_INPUT={input_json}",
                "--env", f"SPANTRACE_EXECUTION_ADAPTER={adapter}",
                "--env", f"SPANTRACE_CAPTURE_PAYLOADS={str(capture_payloads).lower()}",
                "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--env", "PYTHONUNBUFFERED=1",
                self.settings.execution_worker_image,
                "--source-root", "/workspace/source",
                "--entry-file", execution.entry_file_path,
                "--entry-symbol", execution.entry_symbol,
            ]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            with self._lock:
                self._processes[execution_id] = (process, container)
            execution.worker_container_id = container
            db.commit()
            db.refresh(execution)
            if execution.status == "cancel_requested" or execution.cancel_requested_at is not None:
                self._kill_container(container)
                self._stop_process(process)
                with self._lock:
                    self._processes.pop(execution_id, None)
                self._set_status(execution_id, "cancelled", failure_category="cancelled", exit_code=process.returncode)
                return
            transition_status(execution, "running")
            execution.started_at = execution.started_at or datetime.utcnow()
            db.commit()
            output: list[str] = []
            reader = threading.Thread(target=self._drain_output, args=(process, output), daemon=True)
            reader.start()
            deadline = time.monotonic() + execution.timeout_seconds
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            timed_out = process.poll() is None
            if timed_out:
                self._kill_container(container)
                self._stop_process(process)
            reader.join(timeout=5)
            code = process.returncode
            logs = "".join(output)
            with self._lock:
                self._processes.pop(execution_id, None)
            db2 = self.session_factory()
            try:
                current = db2.get(ExecutionRun, execution_id)
                if not current:
                    return
                if timed_out:
                    target, category = "timed_out", "timeout"
                elif current.status == "cancel_requested":
                    target, category = "cancelled", "cancelled"
                elif code == 0:
                    target, category = "succeeded", None
                else:
                    target, category = "failed", "workflow_exception" if "Traceback" in logs or "Exception" in logs else "nonzero_exit"
                try:
                    transition_status(current, target)
                except ValueError:
                    return
                current.exit_code = code
                current.failure_category = category
                current.completed_at = datetime.utcnow()
                current.logs_text = redact_text(logs, self.settings.execution_log_bytes)
                parsed = self._result_from_logs(logs)
                current.result_json = redact_value(parsed or {})
                db2.commit()
            finally:
                db2.close()
        except Exception as exc:
            self._set_status(execution_id, "infrastructure_error", failure_category="worker_startup", logs=str(exc))
        finally:
            db.close()
            with self._lock:
                self._futures.pop(execution_id, None)
                self._tokens.pop(execution_id, None)
                self._inputs.pop(execution_id, None)

    def _drain_output(self, process: subprocess.Popen[str], output: list[str]) -> None:
        if not process.stdout:
            return
        size = 0
        for line in process.stdout:
            if size < self.settings.execution_log_bytes:
                output.append(line)
                size += len(line.encode("utf-8", errors="replace"))

    @staticmethod
    def _result_from_logs(logs: str) -> dict[str, Any] | None:
        for line in reversed(logs.splitlines()):
            if line.startswith("SPANTRACE_RESULT="):
                try:
                    value = json.loads(line.split("=", 1)[1])
                    return value if isinstance(value, dict) else {"value": value}
                except json.JSONDecodeError:
                    return {"raw_result": line.split("=", 1)[1]}
        return None

    @staticmethod
    def _kill_container(container: str) -> None:
        subprocess.run(["docker", "kill", container], capture_output=True, text=True, timeout=15, check=False)
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, text=True, timeout=15, check=False)

    @staticmethod
    def _stop_process(process: subprocess.Popen[str]) -> None:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
