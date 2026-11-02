"""Developer-defined contract parsing, persistence helpers, and evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import numbers
from pathlib import Path
import re
from typing import Any, Iterable
from uuid import uuid4

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import Contract, ContractResult, ExecutionRun


logger = logging.getLogger(__name__)

SUPPORTED_PREDICATES = {"eq", "lte", "gte", "sum_equals", "difference_equals"}
PREDICATE_ARGUMENTS: dict[str, tuple[str, ...]] = {
    "eq": ("left", "right"),
    "lte": ("left", "right"),
    "gte": ("left", "right"),
    "sum_equals": ("terms", "target", "tolerance"),
    "difference_equals": ("minuend", "subtrahend", "target", "tolerance"),
}
PATH_RE = re.compile(r"^output\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\*\])*$")
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\[\*\]")
CONTRACT_FILE = Path(".spantrace") / "contracts.yaml"


@dataclass(frozen=True)
class ContractDefinition:
    id: str
    description: str
    predicate: str
    arguments: dict[str, Any]


class ContractValidationError(ValueError):
    """A contract document or record does not meet the supported contract schema."""


def _contract_label(contract_id: Any) -> str:
    value = str(contract_id or "<missing>").strip()
    return value or "<missing>"


def _is_number(value: Any) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def validate_contract(contract_id: Any, description: Any, predicate: Any, arguments: Any) -> ContractDefinition:
    """Validate one contract and return its normalized representation."""

    label = _contract_label(contract_id)
    problems: list[str] = []
    if not isinstance(contract_id, str) or not contract_id.strip():
        problems.append("id is required")
    if not isinstance(description, str) or not description.strip():
        problems.append("description is required")
    if not isinstance(predicate, str) or predicate.strip() not in SUPPORTED_PREDICATES:
        problems.append(f"unknown predicate {predicate!r}")
    if not isinstance(arguments, dict):
        problems.append("predicate arguments must be a mapping")
        arguments = {}
    normalized_arguments = dict(arguments)
    if isinstance(predicate, str) and predicate.strip() in PREDICATE_ARGUMENTS:
        expected = set(PREDICATE_ARGUMENTS[predicate.strip()])
        unknown = sorted(set(normalized_arguments) - expected)
        if unknown:
            problems.append(f"unsupported argument(s): {', '.join(unknown)}")
        for name in PREDICATE_ARGUMENTS[predicate.strip()]:
            if name not in normalized_arguments or normalized_arguments[name] is None or normalized_arguments[name] == "":
                problems.append(f"missing argument '{name}'")
        for name, value in normalized_arguments.items():
            if name not in expected:
                continue
            if name == "tolerance":
                if not _is_number(value):
                    problems.append("argument 'tolerance' must be numeric")
                elif value < 0:
                    problems.append("negative tolerance is not allowed")
                continue
            if not isinstance(value, str) or not PATH_RE.fullmatch(value):
                problems.append(f"argument '{name}' must be a path starting with output.")
        if predicate.strip() == "sum_equals" and isinstance(normalized_arguments.get("terms"), str) and "[*]" not in normalized_arguments["terms"]:
            problems.append("argument 'terms' must use [*] for list projection")
        if predicate.strip() != "sum_equals" and any("[*]" in str(normalized_arguments.get(name, "")) for name in expected if name != "tolerance"):
            problems.append("list projection [*] is only supported in sum_equals terms")
    if problems:
        raise ContractValidationError(f"Contract {label}: {'; '.join(problems)}")
    return ContractDefinition(id=label, description=description.strip(), predicate=predicate.strip(), arguments=normalized_arguments)


def _mapping_arguments(raw: dict[str, Any]) -> dict[str, Any]:
    direct = {key: value for key, value in raw.items() if key not in {"id", "description", "predicate", "status", "version"}}
    nested = raw.get("arguments")
    if nested is not None:
        if not isinstance(nested, dict):
            return {"__invalid_arguments__": nested}
        return {**nested, **{key: value for key, value in direct.items() if key != "arguments"}}
    return direct


def parse_contract_document(document: str | bytes) -> list[ContractDefinition]:
    """Parse and validate a YAML contracts document."""

    try:
        loaded = yaml.safe_load(document) or {}
    except yaml.YAMLError as exc:
        raise ContractValidationError(f"Contract <document>: invalid YAML: {exc}") from exc
    if not isinstance(loaded, dict) or not isinstance(loaded.get("contracts"), list):
        raise ContractValidationError("Contract <document>: the top-level contracts list is required")
    definitions: list[ContractDefinition] = []
    seen: set[str] = set()
    for raw in loaded["contracts"]:
        if not isinstance(raw, dict):
            raise ContractValidationError("Contract <missing>: each contract must be a mapping")
        contract_id = _contract_label(raw.get("id"))
        if contract_id in seen:
            raise ContractValidationError(f"Contract {contract_id}: duplicate id")
        seen.add(contract_id)
        definitions.append(validate_contract(contract_id, raw.get("description"), raw.get("predicate"), _mapping_arguments(raw)))
    return definitions


def load_contracts_from_snapshot(root: str | Path) -> list[ContractDefinition]:
    """Read the optional contract file from an already safely extracted snapshot."""

    path = Path(root).resolve() / CONTRACT_FILE
    if path.is_symlink() or not path.is_file():
        return []
    try:
        if path.stat().st_size > 1 * 1024 * 1024:
            raise ContractValidationError("Contract <document>: .spantrace/contracts.yaml exceeds the 1 MiB limit")
        return parse_contract_document(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise ContractValidationError(f"Contract <document>: .spantrace/contracts.yaml could not be read: {exc}") from exc


def _arguments_for_payload(payload: Any) -> dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    nested = data.pop("arguments", {}) or {}
    for key in {"id", "description", "predicate", "analysis_id"}:
        data.pop(key, None)
    return {**nested, **data}


def contract_definition_from_payload(payload: Any) -> ContractDefinition:
    return validate_contract(payload.id, payload.description, payload.predicate, _arguments_for_payload(payload))


def serialize_contract(contract: Contract) -> dict[str, Any]:
    return {
        "record_id": contract.record_id,
        "id": contract.id,
        "version": contract.version,
        "project_id": contract.project_id,
        "source_analysis_id": contract.source_analysis_id,
        "description": contract.description,
        "status": contract.status,
        "approved_by": contract.approved_by,
        "approved_at": contract.approved_at.isoformat() + "Z" if contract.approved_at else None,
        "predicate": contract.predicate,
        "arguments": contract.arguments_json or {},
        "created_at": contract.created_at.isoformat() + "Z",
        "updated_at": contract.updated_at.isoformat() + "Z",
    }


def serialize_contract_result(result: ContractResult) -> dict[str, Any]:
    return {
        "id": result.id,
        "contract_id": result.contract.id if result.contract else None,
        "contract_version": result.contract.version if result.contract else None,
        "execution_id": result.execution_id,
        "status": result.status,
        "reason": result.reason,
        "details": result.details_json or {},
        "evaluated_at": result.evaluated_at.isoformat() + "Z",
    }


def latest_contract(db: Session, project_id: str, contract_id: str) -> Contract | None:
    return db.scalar(select(Contract).where(Contract.project_id == project_id, Contract.id == contract_id).order_by(Contract.version.desc()))


def latest_contracts(db: Session, project_id: str) -> list[Contract]:
    rows = db.scalars(select(Contract).where(Contract.project_id == project_id).order_by(Contract.id, Contract.version.desc())).all()
    latest: dict[str, Contract] = {}
    for row in rows:
        latest.setdefault(row.id, row)
    return sorted(latest.values(), key=lambda item: item.id)


def create_contract_record(db: Session, project_id: str, definition: ContractDefinition, *, source_analysis_id: str | None = None) -> Contract:
    if latest_contract(db, project_id, definition.id):
        raise ContractValidationError(f"Contract {definition.id}: a version already exists; edit the existing contract")
    row = Contract(record_id=str(uuid4()), project_id=project_id, id=definition.id, version=1, source_analysis_id=source_analysis_id, description=definition.description, status="draft", predicate=definition.predicate, arguments_json=definition.arguments)
    db.add(row)
    return row


def edit_contract_record(db: Session, current: Contract, definition: ContractDefinition, *, source_analysis_id: str | None = None) -> Contract:
    if current.status == "approved":
        row = Contract(record_id=str(uuid4()), project_id=current.project_id, id=current.id, version=current.version + 1, source_analysis_id=source_analysis_id if source_analysis_id is not None else current.source_analysis_id, description=definition.description, status="draft", predicate=definition.predicate, arguments_json=definition.arguments)
        db.add(row)
        return row
    current.description = definition.description
    current.predicate = definition.predicate
    current.arguments_json = definition.arguments
    if source_analysis_id is not None:
        current.source_analysis_id = source_analysis_id
    current.updated_at = datetime.utcnow()
    return current


def persist_imported_contracts(db: Session, project_id: str, analysis_id: str, definitions: Iterable[ContractDefinition]) -> list[Contract]:
    rows: list[Contract] = []
    for definition in definitions:
        current = latest_contract(db, project_id, definition.id)
        version = current.version + 1 if current else 1
        row = Contract(record_id=str(uuid4()), project_id=project_id, id=definition.id, version=version, source_analysis_id=analysis_id, description=definition.description, status="draft", predicate=definition.predicate, arguments_json=definition.arguments)
        db.add(row)
        rows.append(row)
    return rows


def _tokens(path: str) -> list[str] | None:
    if not isinstance(path, str) or not PATH_RE.fullmatch(path):
        return None
    suffix = path[len("output."):]
    tokens = TOKEN_RE.findall(suffix)
    return tokens if "".join(tokens) == suffix.replace(".", "") else tokens


def resolve_path(output: Any, path: str) -> tuple[bool, Any]:
    """Resolve an output path, including explicit list projections."""

    tokens = _tokens(path)
    if not tokens:
        return False, None

    def walk(value: Any, remaining: list[str]) -> tuple[bool, Any]:
        if not remaining:
            return True, value
        token, rest = remaining[0], remaining[1:]
        if token == "[*]":
            if not isinstance(value, list):
                return False, None
            values: list[Any] = []
            for item in value:
                found, resolved = walk(item, rest)
                if not found:
                    return False, None
                values.append(resolved)
            return True, values
        if not isinstance(value, dict) or token not in value:
            return False, None
        return walk(value[token], rest)

    return walk(output, tokens)


def _inconclusive(contract_id: str, reason: str) -> dict[str, Any]:
    return {"contract_id": contract_id, "status": "inconclusive", "reason": reason, "details": {}}


def evaluate_definition(definition: ContractDefinition, output: Any) -> dict[str, Any]:
    """Evaluate a validated contract against the workflow's final output."""

    values: dict[str, Any] = {}
    for name, value in definition.arguments.items():
        if name == "tolerance":
            values[name] = value
            continue
        found, resolved = resolve_path(output, value)
        if not found:
            return _inconclusive(definition.id, f"Missing output path for argument '{name}': {value}")
        values[name] = resolved
    numeric_values = [value for name, value in values.items() if name not in {"tolerance", "terms"}]
    if definition.predicate == "sum_equals" and (not isinstance(values.get("terms"), list) or any(not _is_number(value) for value in values["terms"])):
        return _inconclusive(definition.id, "A sum_equals term resolved to a non-numeric value")
    if any(not _is_number(value) for value in numeric_values):
        return _inconclusive(definition.id, "A contract operand resolved to a non-numeric value")
    try:
        if definition.predicate == "eq":
            actual = values["left"] == values["right"]
            details = {"left": values["left"], "right": values["right"]}
        elif definition.predicate == "lte":
            actual = values["left"] <= values["right"]
            details = {"left": values["left"], "right": values["right"]}
        elif definition.predicate == "gte":
            actual = values["left"] >= values["right"]
            details = {"left": values["left"], "right": values["right"]}
        elif definition.predicate == "sum_equals":
            terms = values["terms"]
            if not isinstance(terms, list):
                return _inconclusive(definition.id, "The sum_equals terms path did not resolve to a list")
            actual_value = sum(terms)
            actual = abs(actual_value - values["target"]) <= values["tolerance"]
            details = {"terms": terms, "sum": actual_value, "target": values["target"], "tolerance": values["tolerance"]}
        elif definition.predicate == "difference_equals":
            actual_value = values["minuend"] - values["subtrahend"]
            actual = abs(actual_value - values["target"]) <= values["tolerance"]
            details = {"minuend": values["minuend"], "subtrahend": values["subtrahend"], "difference": actual_value, "target": values["target"], "tolerance": values["tolerance"]}
        else:
            return _inconclusive(definition.id, f"Unsupported predicate: {definition.predicate}")
    except (TypeError, ValueError):
        return _inconclusive(definition.id, "Contract operands could not be compared")
    return {"contract_id": definition.id, "status": "pass" if actual else "fail", "reason": None if actual else "The contract predicate evaluated false", "details": details}


def definition_from_row(contract: Contract) -> ContractDefinition:
    return ContractDefinition(id=contract.id, description=contract.description, predicate=contract.predicate, arguments=contract.arguments_json or {})


def final_output_from_execution(execution: ExecutionRun) -> Any:
    result = execution.result_json or {}
    if isinstance(result, dict) and "output" in result:
        return result["output"]
    return result


def approved_contracts_for_execution(db: Session, execution: ExecutionRun) -> list[Contract]:
    rows = db.scalars(select(Contract).where(Contract.project_id == execution.project_id, Contract.status == "approved").order_by(Contract.id, Contract.version.desc())).all()
    approved: dict[str, Contract] = {}
    for row in rows:
        if row.source_analysis_id not in {None, execution.analysis_id}:
            continue
        approved.setdefault(row.id, row)
    return sorted(approved.values(), key=lambda item: item.id)


def evaluate_execution_contracts(db: Session, execution: ExecutionRun) -> list[ContractResult]:
    results: list[ContractResult] = []
    for contract in approved_contracts_for_execution(db, execution):
        outcome = evaluate_definition(definition_from_row(contract), final_output_from_execution(execution)) if execution.result_json else _inconclusive(contract.id, "The execution has no recorded final output")
        result = db.scalar(select(ContractResult).where(ContractResult.execution_id == execution.id, ContractResult.contract_record_id == contract.record_id))
        if result is None:
            result = ContractResult(id=str(uuid4()), execution_id=execution.id, contract_record_id=contract.record_id, status=outcome["status"], reason=outcome["reason"], details_json=outcome["details"])
            db.add(result)
        else:
            result.status = outcome["status"]
            result.reason = outcome["reason"]
            result.details_json = outcome["details"]
            result.evaluated_at = datetime.utcnow()
        results.append(result)
    db.flush()
    return results


def contract_results_for_execution(db: Session, execution_id: str) -> list[ContractResult]:
    return db.scalars(select(ContractResult).options(selectinload(ContractResult.contract)).where(ContractResult.execution_id == execution_id).order_by(ContractResult.evaluated_at, ContractResult.id)).all()
