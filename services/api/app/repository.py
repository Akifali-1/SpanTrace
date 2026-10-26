"""Safe repository ingestion, persistence, and configuration serialization."""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO
from urllib.parse import quote, urlparse

import httpx
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .config import Settings
from .discovery import EXCLUDED_DIRS, AnalysisResult, analyze_repository, config_for_analysis, redact_source_lines
from .integrations import SUPPORTED_INTEGRATIONS
from .models import InstrumentationConfig, Project, RepositoryAnalysis, RepositoryFinding, RepositoryRelationship
from .schemas import InstrumentationConfigSelection


ALLOWED_ZIP_CONTENT_TYPES = {"", "application/zip", "application/x-zip-compressed", "application/octet-stream"}
GITHUB_HOSTS = {"github.com", "www.github.com"}
DRIVE_PATH_RE = re.compile(r"^[a-zA-Z]:")


class RepositoryImportError(ValueError):
    """An import failed a user-actionable validation or upstream check."""


def _safe_member_name(name: str, max_depth: int) -> str:
    normalized = name.replace("\\", "/")
    if not normalized or normalized.startswith("/") or DRIVE_PATH_RE.match(normalized):
        raise RepositoryImportError("Archive contains an absolute path.")
    if "\x00" in normalized:
        raise RepositoryImportError("Archive contains an invalid path.")
    parts = [part for part in PurePosixPath(normalized).parts if part not in {"."}]
    if not parts or any(part == ".." for part in parts):
        raise RepositoryImportError("Archive contains a path traversal entry.")
    if len(parts) > max_depth:
        raise RepositoryImportError("Archive contains a path deeper than the configured limit.")
    return "/".join(parts)


def _excluded_path(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    return any(part in EXCLUDED_DIRS for part in parts)


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == 0o120000


def safe_extract_zip(archive: BinaryIO, destination: Path, settings: Settings) -> dict[str, Any]:
    """Extract only bounded regular files below ``destination``.

    Archive entries are validated before writes.  Generated/vendor directories
    are intentionally ignored instead of being copied into project storage.
    """

    destination.mkdir(parents=True, exist_ok=False)
    destination = destination.resolve()
    extracted_files = 0
    extracted_bytes = 0
    skipped_files = 0
    seen_paths: set[str] = set()
    try:
        with zipfile.ZipFile(archive) as zipped:
            for info in zipped.infolist():
                relative = _safe_member_name(info.filename, settings.repository_max_depth)
                if relative in seen_paths:
                    raise RepositoryImportError("Archive contains duplicate paths.")
                seen_paths.add(relative)
                if _is_symlink(info):
                    raise RepositoryImportError("Archive symlinks are not accepted.")
                if info.is_dir():
                    continue
                if info.file_size < 0:
                    raise RepositoryImportError("Archive contains an invalid file size.")
                if _excluded_path(relative):
                    skipped_files += 1
                    continue
                extracted_files += 1
                if extracted_files > settings.repository_max_files:
                    raise RepositoryImportError("Archive contains too many source files.")
                if info.file_size > settings.repository_max_file_bytes:
                    raise RepositoryImportError(f"Archive file exceeds the individual file limit: {relative}")
                if extracted_bytes + info.file_size > settings.repository_max_extracted_bytes:
                    raise RepositoryImportError("Archive exceeds the extracted-size limit.")
                target = (destination / relative).resolve()
                try:
                    target.relative_to(destination)
                except ValueError as exc:
                    raise RepositoryImportError("Archive path escapes the extraction directory.") from exc
                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with zipped.open(info, "r") as source, target.open("wb") as output:
                    while True:
                        chunk = source.read(64 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > settings.repository_max_file_bytes or extracted_bytes + written > settings.repository_max_extracted_bytes:
                            raise RepositoryImportError("Archive exceeds the extracted-size limit.")
                        output.write(chunk)
                target.chmod(0o600)
                extracted_bytes += written
    except zipfile.BadZipFile as exc:
        raise RepositoryImportError("The uploaded file is not a valid ZIP archive.") from exc
    except OSError as exc:
        raise RepositoryImportError("The archive could not be safely extracted.") from exc
    return {"extracted_files": extracted_files, "extracted_bytes": extracted_bytes, "skipped_files": skipped_files}


def _github_parts(raw_url: str) -> tuple[str, str]:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in GITHUB_HOSTS:
        raise RepositoryImportError("Only public HTTPS GitHub repository URLs are supported.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise RepositoryImportError("The GitHub repository URL has an invalid port.") from exc
    if parsed.username or parsed.password or port not in {None, 443}:
        raise RepositoryImportError("GitHub repository URLs must not contain credentials or a non-standard port.")
    if parsed.query or parsed.fragment:
        raise RepositoryImportError("Repository URLs must not contain query parameters or fragments.")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[1].endswith(".git"):
        raise RepositoryImportError("Use a repository URL such as https://github.com/owner/repository.")
    owner, repository = parts
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repository):
        raise RepositoryImportError("The GitHub owner or repository name is invalid.")
    return owner, repository


def fetch_public_github_archive(raw_url: str, ref: str | None, settings: Settings) -> tuple[bytes, dict[str, Any]]:
    owner, repository = _github_parts(raw_url)
    api_root = f"https://api.github.com/repos/{owner}/{repository}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "SpanTrace-repository-analysis"}
    try:
        with httpx.Client(timeout=settings.repository_http_timeout_seconds, follow_redirects=False, headers=headers) as client:
            metadata_response = client.get(api_root)
            if metadata_response.status_code in {301, 302, 303, 307, 308}:
                raise RepositoryImportError("GitHub returned an unexpected redirect.")
            if metadata_response.status_code in {401, 403, 404}:
                raise RepositoryImportError("The repository is private, unavailable, or GitHub access was denied. Private repository authorization is not configured.")
            if metadata_response.status_code != 200:
                raise RepositoryImportError("GitHub could not provide repository metadata.")
            try:
                metadata = metadata_response.json()
            except ValueError as exc:
                raise RepositoryImportError("GitHub returned invalid repository metadata.") from exc
            if not isinstance(metadata, dict):
                raise RepositoryImportError("GitHub returned invalid repository metadata.")
            if metadata.get("private"):
                raise RepositoryImportError("Private repository import is not enabled. Use a ZIP upload or configure an authorized read-only integration.")
            selected_ref = ref or metadata.get("default_branch")
            if not selected_ref or len(selected_ref) > 200 or selected_ref.startswith("-"):
                raise RepositoryImportError("GitHub did not provide a usable branch or reference.")
            commit_sha: str | None = None
            commit_response = client.get(f"{api_root}/commits/{quote(selected_ref, safe='')}")
            if commit_response.status_code == 200:
                commit_sha = str(commit_response.json().get("sha") or "") or None
            elif commit_response.status_code in {301, 302, 303, 307, 308}:
                raise RepositoryImportError("GitHub returned an unexpected redirect while resolving the revision.")
            archive_url = f"https://codeload.github.com/{owner}/{repository}/zip/{quote(selected_ref, safe='')}"
            with client.stream("GET", archive_url) as archive_response:
                if archive_response.status_code in {301, 302, 303, 307, 308}:
                    raise RepositoryImportError("GitHub returned an unexpected archive redirect.")
                if archive_response.status_code != 200:
                    raise RepositoryImportError("GitHub could not provide a source archive for that revision.")
                chunks: list[bytes] = []
                size = 0
                for chunk in archive_response.iter_bytes(64 * 1024):
                    size += len(chunk)
                    if size > settings.repository_max_archive_bytes:
                        raise RepositoryImportError("The GitHub archive exceeds the configured archive-size limit.")
                    chunks.append(chunk)
                archive = b"".join(chunks)
    except httpx.TimeoutException as exc:
        raise RepositoryImportError("GitHub repository import timed out. Retry or use a ZIP upload.") from exc
    except httpx.HTTPError as exc:
        raise RepositoryImportError("GitHub repository import failed due to a network error.") from exc
    if len(archive) > settings.repository_max_archive_bytes:
        raise RepositoryImportError("The GitHub archive exceeds the configured archive-size limit.")
    return archive, {
        "name": str(metadata.get("full_name") or f"{owner}/{repository}"),
        "branch": str(selected_ref),
        "commit_sha": commit_sha,
        "source_revision": commit_sha or str(selected_ref),
        "source_url": raw_url.strip(),
    }


def _storage_root(settings: Settings, project_id: str, analysis_id: str) -> Path:
    root = Path(settings.repository_storage_path).expanduser().resolve() / project_id / analysis_id
    root.parent.mkdir(parents=True, exist_ok=True)
    return root


def _new_analysis_version(db: Session, project_id: str, fingerprint: str) -> int:
    value = db.scalar(select(func.max(RepositoryAnalysis.analysis_version)).where(RepositoryAnalysis.project_id == project_id, RepositoryAnalysis.archive_fingerprint == fingerprint))
    return int(value or 0) + 1


def _mark_previous_configs_stale(db: Session, project_id: str) -> None:
    configs = db.scalars(select(InstrumentationConfig).where(InstrumentationConfig.project_id == project_id, InstrumentationConfig.stale.is_(False))).all()
    for config in configs:
        config.stale = True


def _persist_result(db: Session, analysis: RepositoryAnalysis, result: AnalysisResult) -> None:
    finding_rows: dict[str, RepositoryFinding] = {}
    for finding in result.findings:
        row = RepositoryFinding(
            analysis_id=analysis.id,
            stable_id=finding.stable_id,
            kind=finding.kind,
            name=finding.name,
            symbol_type=finding.symbol_type,
            file_path=finding.file_path,
            start_line=finding.start_line,
            end_line=finding.end_line,
            symbol_name=finding.symbol_name,
            framework=finding.framework,
            detection_method=finding.detection_method,
            evidence_summary=finding.evidence_summary,
            confidence=finding.confidence,
            instrumentation_status=finding.instrumentation_status,
            metadata_json=finding.metadata,
        )
        db.add(row)
        finding_rows[finding.stable_id] = row
    db.flush()
    for relationship in result.relationships:
        source = finding_rows.get(relationship.source_stable_id)
        if source is None:
            continue
        target = finding_rows.get(relationship.target_stable_id or "")
        db.add(
            RepositoryRelationship(
                analysis_id=analysis.id,
                source_finding_id=source.id,
                target_finding_id=target.id if target else None,
                target_name=relationship.target_name,
                relationship_type=relationship.relationship_type,
                confidence=relationship.confidence,
                detection_method=relationship.detection_method,
                evidence_summary=relationship.evidence_summary,
                file_path=relationship.file_path,
                start_line=relationship.start_line,
                end_line=relationship.end_line,
                metadata_json=relationship.metadata,
            )
        )


def process_archive(
    db: Session,
    project: Project,
    archive_bytes: bytes,
    *,
    source_kind: str,
    name: str,
    source_url: str | None,
    branch: str | None,
    commit_sha: str | None,
    source_revision: str,
    settings: Settings,
) -> tuple[RepositoryAnalysis, bool]:
    if len(archive_bytes) > settings.repository_max_archive_bytes:
        raise RepositoryImportError("The archive exceeds the configured archive-size limit.")
    fingerprint = hashlib.sha256(archive_bytes).hexdigest()
    existing = db.scalar(
        select(RepositoryAnalysis)
        .where(RepositoryAnalysis.project_id == project.id, RepositoryAnalysis.archive_fingerprint == fingerprint)
        .order_by(RepositoryAnalysis.analysis_version.desc())
    )
    if existing and existing.status in {"analysis_complete", "partially_analyzed"}:
        return existing, True

    analysis = RepositoryAnalysis(
        project_id=project.id,
        name=name[:200],
        source_kind=source_kind,
        source_url=source_url,
        branch=branch,
        commit_sha=commit_sha,
        source_revision=source_revision[:200],
        archive_fingerprint=fingerprint,
        status="importing",
        analysis_version=_new_analysis_version(db, project.id, fingerprint),
    )
    db.add(analysis)
    db.flush()
    root = _storage_root(settings, project.id, analysis.id)
    archive_path: Path | None = None
    try:
        analysis.status = "source_available"
        db.commit()
        with tempfile.NamedTemporaryFile(prefix="archive-", suffix=".zip", dir=root.parent, delete=False) as temporary:
            temporary.write(archive_bytes)
            archive_path = Path(temporary.name)
        with archive_path.open("rb") as archive:
            safe_extract_zip(archive, root, settings)
        analysis.source_path = str(root)
        analysis.status = "analyzing"
        db.commit()
        result = analyze_repository(root, settings)
        _persist_result(db, analysis, result)
        analysis.summary_json = result.summary
        analysis.limitations_json = result.limitations
        analysis.status = "partially_analyzed" if result.partially_analyzed else "analysis_complete"
        analysis.analyzed_at = datetime.utcnow()
        analysis.updated_at = datetime.utcnow()
        _mark_previous_configs_stale(db, project.id)
        db.commit()
        return analysis, False
    except (RepositoryImportError, OSError, zipfile.BadZipFile) as exc:
        db.rollback()
        failed = db.get(RepositoryAnalysis, analysis.id)
        if failed:
            failed.status = "failed"
            failed.error_message = str(exc)[:1000]
            failed.updated_at = datetime.utcnow()
            db.commit()
        shutil.rmtree(root, ignore_errors=True)
        raise RepositoryImportError(str(exc)) from exc
    finally:
        if archive_path:
            archive_path.unlink(missing_ok=True)


async def read_upload(upload: UploadFile, settings: Settings) -> tuple[bytes, str]:
    filename = upload.filename or "repository.zip"
    if not filename.lower().endswith(".zip"):
        raise RepositoryImportError("Upload a ZIP archive with a .zip filename.")
    if (upload.content_type or "") not in ALLOWED_ZIP_CONTENT_TYPES:
        raise RepositoryImportError("The uploaded file must be a ZIP archive.")
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > settings.repository_max_archive_bytes:
            raise RepositoryImportError("The uploaded archive exceeds the configured archive-size limit.")
        chunks.append(chunk)
    if not chunks:
        raise RepositoryImportError("The uploaded archive is empty.")
    return b"".join(chunks), Path(filename).stem[:200] or "Uploaded repository"


def serialize_finding(finding: RepositoryFinding) -> dict[str, Any]:
    return {
        "id": finding.id,
        "finding_id": finding.stable_id,
        "kind": finding.kind,
        "name": finding.name,
        "symbol_type": finding.symbol_type,
        "file_path": finding.file_path,
        "start_line": finding.start_line,
        "end_line": finding.end_line,
        "symbol_name": finding.symbol_name,
        "framework": finding.framework,
        "detection_method": finding.detection_method,
        "evidence_summary": finding.evidence_summary,
        "confidence": finding.confidence,
        "instrumentation_status": finding.instrumentation_status,
        "metadata": finding.metadata_json or {},
    }


def serialize_relationship(relationship: RepositoryRelationship) -> dict[str, Any]:
    return {
        "id": relationship.id,
        "source_finding_id": relationship.source_finding.stable_id if relationship.source_finding else None,
        "target_finding_id": relationship.target_finding.stable_id if relationship.target_finding else None,
        "target_name": relationship.target_name,
        "type": relationship.relationship_type,
        "confidence": relationship.confidence,
        "detection_method": relationship.detection_method,
        "evidence_summary": relationship.evidence_summary,
        "file_path": relationship.file_path,
        "start_line": relationship.start_line,
        "end_line": relationship.end_line,
        "metadata": relationship.metadata_json or {},
    }


def serialize_config(config: InstrumentationConfig | None) -> dict[str, Any] | None:
    if config is None:
        return None
    return {"id": config.id, "analysis_id": config.analysis_id, "version": config.version, "valid": config.valid, "stale": config.stale, "created_at": config.created_at.isoformat() + "Z", "updated_at": config.updated_at.isoformat() + "Z", "config": config.config_json}


def serialize_analysis(analysis: RepositoryAnalysis, *, include_findings: bool = False) -> dict[str, Any]:
    result = {
        "id": analysis.id,
        "name": analysis.name,
        "source_kind": analysis.source_kind,
        "source_url": analysis.source_url,
        "branch": analysis.branch,
        "commit_sha": analysis.commit_sha,
        "source_revision": analysis.source_revision,
        "archive_fingerprint": analysis.archive_fingerprint,
        "status": analysis.status,
        "analysis_version": analysis.analysis_version,
        "summary": analysis.summary_json or {},
        "limitations": analysis.limitations_json or [],
        "error_message": analysis.error_message,
        "created_at": analysis.created_at.isoformat() + "Z",
        "updated_at": analysis.updated_at.isoformat() + "Z",
        "analyzed_at": analysis.analyzed_at.isoformat() + "Z" if analysis.analyzed_at else None,
    }
    if include_findings:
        result["findings"] = [serialize_finding(finding) for finding in analysis.findings]
        result["relationships"] = [serialize_relationship(relationship) for relationship in analysis.relationships]
        latest_config = max(analysis.configurations, key=lambda item: item.version, default=None)
        result["configuration"] = serialize_config(latest_config)
    return result


def load_analysis(db: Session, project_id: str, analysis_id: str) -> RepositoryAnalysis | None:
    return db.scalar(
        select(RepositoryAnalysis)
        .options(selectinload(RepositoryAnalysis.findings), selectinload(RepositoryAnalysis.relationships).selectinload(RepositoryRelationship.source_finding), selectinload(RepositoryAnalysis.relationships).selectinload(RepositoryRelationship.target_finding), selectinload(RepositoryAnalysis.configurations))
        .where(RepositoryAnalysis.id == analysis_id, RepositoryAnalysis.project_id == project_id)
    )


def save_configuration(db: Session, project: Project, analysis: RepositoryAnalysis, selection: InstrumentationConfigSelection) -> InstrumentationConfig:
    findings = list(analysis.findings)
    try:
        config_json = config_for_analysis(project=project, analysis=analysis, findings=findings, selection=selection, adapters=list(SUPPORTED_INTEGRATIONS))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    latest_version = db.scalar(select(func.max(InstrumentationConfig.version)).where(InstrumentationConfig.analysis_id == analysis.id)) or 0
    config = InstrumentationConfig(project_id=project.id, analysis_id=analysis.id, version=int(latest_version) + 1, config_json=config_json, valid=True, stale=False)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def read_source_evidence(analysis: RepositoryAnalysis, path: str, start_line: int, end_line: int) -> dict[str, Any]:
    if not analysis.source_path:
        raise HTTPException(status_code=404, detail="Source is not available for this analysis.")
    relative = _safe_member_name(path, 40)
    root = Path(analysis.source_path).resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Source path is outside the imported repository.") from exc
    if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size > 2 * 1024 * 1024:
        raise HTTPException(status_code=404, detail="Source evidence is unavailable for this path.")
    try:
        lines = candidate.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=404, detail="Source evidence is not a readable text file.") from exc
    return {"path": relative, "start_line": max(1, start_line), "end_line": max(start_line, end_line), "lines": redact_source_lines(lines, start_line, end_line)}
