"""Deterministic, read-only repository discovery.

The analyzer deliberately works on source text and Python ASTs only.  It never
imports a project module, invokes a discovered function, installs dependencies,
or runs a repository-provided command.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings
from .schemas import InstrumentationConfigDocument


EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "coverage",
    "htmlcov",
    "target",
    "vendor",
    "generated",
    "out",
}
LANGUAGE_BY_SUFFIX = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
}
MANIFEST_NAMES = {
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
    "poetry.lock",
    "uv.lock",
    "Pipfile",
    "Pipfile.lock",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
    "Dockerfile",
}
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth(?:orization)?|password|secret)\s*([:=])\s*(?:\"[^\"\n]*\"|'[^'\n]*'|[^\s,;]+)"
)
ENV_NAME_RE = re.compile(
    r"(?:os\.(?:environ|getenv)|environ)\s*(?:\[\s*[\"']([^\"']+)[\"']\s*\]|\(\s*[\"']([^\"']+)[\"'])"
)
ENV_TEMPLATE_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]{2,})\}")

CONFIDENCE_RANK = {
    "unknown": 0,
    "possible": 1,
    "strong_candidate": 2,
    "confirmed_syntax": 3,
}


@dataclass
class FindingData:
    stable_id: str
    kind: str
    name: str
    symbol_type: str | None
    file_path: str
    start_line: int
    end_line: int
    symbol_name: str | None
    framework: str | None
    detection_method: str
    evidence_summary: str
    confidence: str
    instrumentation_status: str = "needs_confirmation"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RelationshipData:
    source_stable_id: str
    target_stable_id: str | None
    target_name: str | None
    relationship_type: str
    confidence: str
    detection_method: str
    evidence_summary: str
    file_path: str
    start_line: int
    end_line: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    findings: list[FindingData]
    relationships: list[RelationshipData]
    summary: dict[str, Any]
    limitations: list[str]
    partially_analyzed: bool = False


def stable_id(kind: str, file_path: str, symbol_name: str | None) -> str:
    value = f"{kind}:{file_path}:{symbol_name or ''}"
    return f"st_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


def _line_range(node: ast.AST) -> tuple[int, int]:
    line = int(getattr(node, "lineno", 1))
    end_line = int(getattr(node, "end_lineno", line))
    return line, end_line


def _call_name(node: ast.Call) -> str:
    value: ast.AST = node.func
    parts: list[str] = []
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts)) or "call"


def _decorator_name(node: ast.AST) -> str:
    value = node
    if isinstance(value, ast.Call):
        value = value.func
    if isinstance(value, ast.Attribute):
        return value.attr.lower()
    if isinstance(value, ast.Name):
        return value.id.lower()
    return ""


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _redact_line(value: str) -> str:
    return SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value)


def redact_source_lines(lines: list[str], start_line: int, end_line: int, *, max_lines: int = 80) -> list[dict[str, Any]]:
    start = max(1, start_line)
    end = min(len(lines), max(start, end_line), start + max_lines - 1)
    return [{"line": number, "text": _redact_line(lines[number - 1])} for number in range(start, end + 1)]


def _language_for(path: Path) -> str:
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "Other")


def _is_manifest(path: Path) -> bool:
    return path.name in MANIFEST_NAMES or path.name.startswith("requirements") and path.suffix == ".txt"


def _framework_from_import(name: str) -> str | None:
    lowered = name.lower()
    if lowered.startswith("opentelemetry"):
        return "OpenTelemetry"
    if lowered.startswith("spantrace") or lowered.startswith("agentscope"):
        return "SpanTrace"
    if lowered.startswith("langgraph"):
        return "LangGraph"
    if lowered.startswith("langchain"):
        return "LangChain"
    if lowered.startswith("crewai"):
        return "CrewAI"
    if lowered.startswith("autogen") or lowered.startswith("microsoft.autogen"):
        return "AutoGen"
    if lowered.startswith("openai"):
        return "OpenAI"
    if lowered.startswith("anthropic"):
        return "Anthropic"
    if lowered.startswith("google.generativeai") or lowered.startswith("google.genai"):
        return "Google GenAI"
    if lowered.startswith("litellm"):
        return "LiteLLM"
    return None


def _framework_instrumentation(framework: str | None) -> str:
    if framework in {"OpenTelemetry", "SpanTrace"}:
        return "supported_automatic"
    if framework in {"LangGraph", "LangChain", "CrewAI", "AutoGen"}:
        return "explicit_recommended"
    if framework in {"OpenAI", "Anthropic", "Google GenAI"}:
        return "needs_confirmation"
    return "unsupported"


KNOWN_DEPENDENCY_FRAMEWORKS = {
    "opentelemetry-api": "OpenTelemetry",
    "opentelemetry-sdk": "OpenTelemetry",
    "spantrace": "SpanTrace",
    "agentscope": "SpanTrace",
    "langgraph": "LangGraph",
    "langchain": "LangChain",
    "langchain-core": "LangChain",
    "crewai": "CrewAI",
    "autogen": "AutoGen",
    "microsoft-autogen": "AutoGen",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google-generativeai": "Google GenAI",
    "google-genai": "Google GenAI",
    "litellm": "LiteLLM",
}


def _framework_from_dependency(name: str) -> str | None:
    normalized = name.strip().lower().replace("_", "-")
    normalized = normalized.split("[", 1)[0]
    return KNOWN_DEPENDENCY_FRAMEWORKS.get(normalized)


def _manifest_frameworks(path: str, text: str) -> list[tuple[str, int]]:
    """Find known dependency names without evaluating manifest content.

    The parser intentionally treats manifests as data only. TOML/JSON parsing
    improves precision for common manifests; the bounded marker scan keeps
    lockfiles useful without adding a dependency resolver.
    """

    names: set[str] = set()
    suffix = Path(path).suffix.lower()
    if Path(path).name == "pyproject.toml":
        try:
            document = tomllib.loads(text)
            project = document.get("project", {})
            if isinstance(project, dict):
                dependencies = project.get("dependencies", [])
                if isinstance(dependencies, list):
                    names.update(re.split(r"[<>=!~;\s\[]", str(value), maxsplit=1)[0] for value in dependencies)
                optional = project.get("optional-dependencies", {})
                if isinstance(optional, dict):
                    for values in optional.values():
                        if isinstance(values, list):
                            names.update(re.split(r"[<>=!~;\s\[]", str(value), maxsplit=1)[0] for value in values)
            poetry = document.get("tool", {}).get("poetry", {}) if isinstance(document.get("tool", {}), dict) else {}
            if isinstance(poetry, dict) and isinstance(poetry.get("dependencies"), dict):
                names.update(str(value) for value in poetry["dependencies"].keys())
        except (tomllib.TOMLDecodeError, TypeError, ValueError):
            pass
    elif Path(path).name == "package.json":
        try:
            document = json.loads(text)
            if isinstance(document, dict):
                for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                    dependencies = document.get(key, {})
                    if isinstance(dependencies, dict):
                        names.update(str(value) for value in dependencies)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    elif suffix == ".txt" or Path(path).name in {"Pipfile", "Pipfile.lock"}:
        for line in text.splitlines():
            value = line.split("#", 1)[0].strip()
            if value and not value.startswith(("-", "[")):
                names.add(re.split(r"[<>=!~;\s\[]", value, maxsplit=1)[0])

    # Lockfiles and malformed manifests still get only exact known-name
    # markers. This avoids treating arbitrary prose as a dependency.
    for dependency in KNOWN_DEPENDENCY_FRAMEWORKS:
        if re.search(rf"(?i)(?<![A-Za-z0-9_.-]){re.escape(dependency)}(?![A-Za-z0-9_.-])", text):
            names.add(dependency)

    result: list[tuple[str, int]] = []
    for name in sorted(names):
        framework = _framework_from_dependency(name)
        if not framework:
            continue
        match = re.search(rf"(?i)(?<![A-Za-z0-9_.-]){re.escape(name)}(?![A-Za-z0-9_.-])", text)
        line = text[: match.start()].count("\n") + 1 if match else 1
        result.append((framework, line))
    return result


def _iter_source_files(root: Path, settings: Settings) -> tuple[list[dict[str, Any]], list[str]]:
    files: list[dict[str, Any]] = []
    limitations: list[str] = []
    total_bytes = 0
    for current, directories, names in os.walk(root):
        directories[:] = sorted(name for name in directories if name not in EXCLUDED_DIRS and not name.startswith("."))
        for name in sorted(names):
            path = Path(current) / name
            if path.is_symlink():
                limitations.append(f"Skipped symlink: {path.relative_to(root).as_posix()}")
                continue
            try:
                size = path.stat().st_size
            except OSError:
                limitations.append(f"Could not stat: {path.relative_to(root).as_posix()}")
                continue
            relative = path.relative_to(root).as_posix()
            language = _language_for(path)
            item: dict[str, Any] = {"path": relative, "language": language, "size": size, "manifest": _is_manifest(path)}
            if size > settings.repository_max_file_bytes:
                limitations.append(f"Skipped oversized file: {relative}")
                item["skipped"] = "file_size_limit"
                files.append(item)
                continue
            if total_bytes + size > settings.repository_analysis_max_source_bytes:
                limitations.append(f"Analysis source limit reached before: {relative}")
                item["skipped"] = "analysis_size_limit"
                files.append(item)
                continue
            try:
                raw = path.read_bytes()
                text = raw.decode("utf-8-sig")
            except (OSError, UnicodeDecodeError):
                item["skipped"] = "not_utf8_text"
                files.append(item)
                continue
            total_bytes += size
            item.update({"text": text, "line_count": len(text.splitlines())})
            files.append(item)
    return files, limitations


def _find_or_add(
    findings: dict[str, FindingData],
    *,
    kind: str,
    name: str,
    file_path: str,
    start_line: int,
    end_line: int,
    symbol_name: str | None,
    symbol_type: str | None,
    framework: str | None,
    detection_method: str,
    evidence_summary: str,
    confidence: str,
    instrumentation_status: str = "needs_confirmation",
    metadata: dict[str, Any] | None = None,
) -> FindingData:
    identifier = stable_id(kind, file_path, symbol_name or f"{name}:{start_line}")
    current = findings.get(identifier)
    if current is None:
        current = FindingData(
            stable_id=identifier,
            kind=kind,
            name=name,
            symbol_type=symbol_type,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            symbol_name=symbol_name,
            framework=framework,
            detection_method=detection_method,
            evidence_summary=evidence_summary,
            confidence=confidence,
            instrumentation_status=instrumentation_status,
            metadata=metadata or {},
        )
        findings[identifier] = current
    elif CONFIDENCE_RANK.get(confidence, 0) > CONFIDENCE_RANK.get(current.confidence, 0):
        current.confidence = confidence
        current.detection_method = detection_method
        current.evidence_summary = evidence_summary
    return current


def _add_relationship(
    relationships: dict[tuple[str, str | None, str, int], RelationshipData],
    *,
    source: FindingData,
    target: FindingData | None,
    target_name: str | None,
    relationship_type: str,
    confidence: str,
    detection_method: str,
    evidence_summary: str,
    file_path: str,
    line: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    key = (source.stable_id, target.stable_id if target else target_name, relationship_type, line)
    relationships.setdefault(
        key,
        RelationshipData(
            source_stable_id=source.stable_id,
            target_stable_id=target.stable_id if target else None,
            target_name=target_name,
            relationship_type=relationship_type,
            confidence=confidence,
            detection_method=detection_method,
            evidence_summary=evidence_summary,
            file_path=file_path,
            start_line=line,
            end_line=line,
            metadata=metadata or {},
        ),
    )


def _module_imports(tree: ast.AST) -> tuple[set[str], dict[str, int]]:
    imports: set[str] = set()
    import_lines: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
                import_lines.setdefault(alias.name, int(getattr(node, "lineno", 1)))
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
            import_lines.setdefault(node.module, int(getattr(node, "lineno", 1)))
    return imports, import_lines


def _find_symbol_calls(node: ast.AST) -> list[ast.Call]:
    return [item for item in ast.walk(node) if isinstance(item, ast.Call)]


def _call_has_model_signal(call_name: str, imports: set[str]) -> bool:
    lowered = call_name.lower()
    provider_import = any(
        any(item.startswith(prefix) for prefix in ("openai", "anthropic", "google", "langchain", "litellm"))
        for item in imports
    )
    if not provider_import:
        return False
    if lowered.startswith(("graph.", "workflow.", "state_graph.", "message_graph.")):
        return False
    return any(
        prefix in lowered
        for prefix in (
            "chat.completions.create",
            "responses.create",
            "messages.create",
            "completions.create",
            "generate_content",
            "completion",
            "invoke",
            "ainvoke",
            "predict",
        )
    )


def _call_has_external_signal(call_name: str, imports: set[str]) -> bool:
    lowered = call_name.lower()
    has_client = any(item.split(".")[0] in {"requests", "httpx", "boto3", "urllib", "grpc"} for item in imports)
    return has_client and (lowered.endswith((".get", ".post", ".put", ".delete", ".request", ".send")) or lowered in {"get", "post", "request"})


def _function_nodes(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _class_nodes(tree: ast.AST) -> list[ast.ClassDef]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]


def _function_name_from_call(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _analyze_python_file(
    item: dict[str, Any],
    findings: dict[str, FindingData],
    relationships: dict[tuple[str, str | None, str, int], RelationshipData],
    frameworks: dict[str, dict[str, Any]],
) -> bool:
    path = str(item["path"])
    text = str(item["text"])
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as error:
        item["parse_error"] = f"line {error.lineno or 1}: invalid Python syntax"
        return False

    imports, import_lines = _module_imports(tree)
    file_frameworks = sorted({framework for framework in (_framework_from_import(name) for name in imports) if framework})
    for framework in file_frameworks:
        frameworks.setdefault(framework, {"name": framework, "files": [], "evidence": []})
        frameworks[framework]["files"].append(path)
        frameworks[framework]["evidence"].append(f"{path}:{import_lines.get(next(name for name in imports if _framework_from_import(name) == framework), 1)} import")
        _find_or_add(
            findings,
            kind="framework",
            name=framework,
            file_path=path,
            start_line=import_lines.get(next(name for name in imports if _framework_from_import(name) == framework), 1),
            end_line=import_lines.get(next(name for name in imports if _framework_from_import(name) == framework), 1),
            symbol_name=framework.lower().replace(" ", "_"),
            symbol_type="import",
            framework=framework,
            detection_method="import analysis",
            evidence_summary=f"Imports {framework} APIs in this module.",
            confidence="confirmed_syntax",
            instrumentation_status=_framework_instrumentation(framework),
        )

    instrumentation_import = any(name.startswith(("spantrace", "agentscope", "opentelemetry")) for name in imports)
    if instrumentation_import:
        line = min((line for name, line in import_lines.items() if name.startswith(("spantrace", "agentscope", "opentelemetry"))), default=1)
        _find_or_add(
            findings,
            kind="instrumentation",
            name="Existing telemetry setup",
            file_path=path,
            start_line=line,
            end_line=line,
            symbol_name=f"telemetry:{line}",
            symbol_type="import",
            framework="SpanTrace" if any(name.startswith(("spantrace", "agentscope")) for name in imports) else "OpenTelemetry",
            detection_method="import analysis",
            evidence_summary="The module imports an existing SpanTrace or OpenTelemetry integration.",
            confidence="confirmed_syntax",
            instrumentation_status="already_configured",
        )

    functions = _function_nodes(tree)
    classes = _class_nodes(tree)
    local_names = {node.name for node in functions + classes}
    function_findings: dict[str, FindingData] = {}
    class_findings: dict[str, FindingData] = {}
    node_owners: dict[int, FindingData] = {}

    for node in classes:
        line, end_line = _line_range(node)
        decorators = {_decorator_name(decorator) for decorator in node.decorator_list}
        bases = [ast.unparse(base) if hasattr(ast, "unparse") else "" for base in node.bases]
        base_text = " ".join(bases).lower()
        agent_base_signal = any(name in base_text for name in ("agent", "assistant"))
        agent_decorator_signal = "agent" in decorators
        agent_name_signal = bool(re.search(r"(?:^|_)(agent|assistant)$", node.name, re.IGNORECASE)) or bool(re.search(r"(?:agent|assistant)(?:manager|worker)$", node.name, re.IGNORECASE))
        behavior_signal = any(
            isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
            and member.name.lower() in {"run", "invoke", "plan", "act", "respond", "execute", "process", "chat"}
            for member in node.body
        )
        agent_signal = agent_base_signal or agent_decorator_signal or (agent_name_signal and behavior_signal)
        if not agent_signal:
            continue
        confidence = "confirmed_syntax" if agent_base_signal or agent_decorator_signal else "strong_candidate"
        finding = _find_or_add(
            findings,
            kind="agent",
            name=node.name,
            file_path=path,
            start_line=line,
            end_line=end_line,
            symbol_name=node.name,
            symbol_type="class",
            framework=file_frameworks[0] if file_frameworks else None,
            detection_method="AST class/base/decorator analysis",
            evidence_summary=f"Class {node.name} has agent-like bases/decorators or a role-specific agent name.",
            confidence=confidence,
            instrumentation_status="explicit_recommended" if not instrumentation_import else "already_configured",
        )
        class_findings[node.name] = finding
        node_owners[id(node)] = finding

    for node in functions:
        line, end_line = _line_range(node)
        decorators = {_decorator_name(decorator) for decorator in node.decorator_list}
        calls = _find_symbol_calls(node)
        call_names = {_call_name(call) for call in calls}
        tool_name_signal = bool(re.search(r"(?:^|_)(tool|tool_fn|function_tool)(?:$|_)", node.name, re.IGNORECASE))
        tool_signal = bool(decorators & {"tool", "function_tool", "register_tool"}) or tool_name_signal
        route_signal = bool(decorators & {"entrypoint", "workflow", "router", "task", "command", "on_event"})
        graph_signal = any(name.endswith((".invoke", ".ainvoke", ".stream", ".astream")) or "graph" in name.lower() for name in call_names)
        model_signal = any(_call_has_model_signal(name, imports) for name in call_names)
        delegation_signal = any(name.rsplit(".", 1)[-1].lower() in {"handoff", "delegate", "delegate_to", "transfer_to", "send_to"} or ".handoff" in name.lower() for name in call_names)
        entry_signal = route_signal or graph_signal or node.name.lower() in {"main", "cli", "run_workflow", "execute_workflow", "workflow"}
        if tool_signal:
            finding = _find_or_add(
                findings,
                kind="tool",
                name=node.name,
                file_path=path,
                start_line=line,
                end_line=end_line,
                symbol_name=node.name,
                symbol_type="function",
                framework=file_frameworks[0] if file_frameworks else None,
                detection_method="AST decorator/name analysis",
                evidence_summary=f"Function {node.name} is marked or named as a tool and is a candidate tool boundary.",
                confidence="confirmed_syntax" if decorators & {"tool", "function_tool", "register_tool"} else "possible",
                instrumentation_status="explicit_recommended" if not instrumentation_import else "already_configured",
            )
            function_findings[node.name] = finding
            node_owners[id(node)] = finding
        elif entry_signal:
            finding = _find_or_add(
                findings,
                kind="workflow_entry",
                name=node.name,
                file_path=path,
                start_line=line,
                end_line=end_line,
                symbol_name=node.name,
                symbol_type="async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                framework=file_frameworks[0] if file_frameworks else None,
                detection_method="AST entry-point/decorator/call analysis",
                evidence_summary=("Function is decorated as a workflow/route entry point." if route_signal else "Function calls a graph/model invocation or uses a conventional workflow entry-point name."),
                confidence="confirmed_syntax" if route_signal else "strong_candidate" if graph_signal else "possible",
                instrumentation_status="explicit_recommended" if not instrumentation_import else "already_configured",
            )
            function_findings[node.name] = finding
            node_owners[id(node)] = finding
        elif model_signal or delegation_signal:
            finding = _find_or_add(
                findings,
                kind="agent",
                name=node.name,
                file_path=path,
                start_line=line,
                end_line=end_line,
                symbol_name=node.name,
                symbol_type="async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                framework=file_frameworks[0] if file_frameworks else None,
                detection_method="AST model/delegation call analysis",
                evidence_summary=(
                    f"Function {node.name} contains a detected model invocation."
                    if model_signal
                    else f"Function {node.name} contains a delegation or handoff call."
                ),
                confidence="strong_candidate",
                instrumentation_status="explicit_recommended" if not instrumentation_import else "already_configured",
            )
            function_findings[node.name] = finding
            node_owners[id(node)] = finding
    graph_findings: list[FindingData] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        called = _call_name(value)
        if not any(token in called.lower() for token in ("stategraph", "messagegraph", "workflow", "graph")):
            continue
        targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        name = targets[0] if targets else "workflow graph"
        line, end_line = _line_range(node)
        graph = _find_or_add(
            findings,
            kind="workflow_graph",
            name=name,
            file_path=path,
            start_line=line,
            end_line=end_line,
            symbol_name=name,
            symbol_type="assignment",
            framework=file_frameworks[0] if file_frameworks else None,
            detection_method="AST graph-construction call analysis",
            evidence_summary=f"Assignment constructs a graph-like object via {called}.",
            confidence="confirmed_syntax",
            instrumentation_status="explicit_recommended" if not instrumentation_import else "already_configured",
        )
        graph_findings.append(graph)

    # A module guard is strong evidence that a conventional main function is a
    # real entry point, even when it does not use a known framework.
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        if not (isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__"):
            continue
        if not any(isinstance(comparator, ast.Constant) and comparator.value == "__main__" for comparator in node.test.comparators):
            continue
        for call in _find_symbol_calls(node):
            called_name = _function_name_from_call(call)
            if not called_name or called_name not in local_names:
                continue
            call_line, _ = _line_range(call)
            function = function_findings.get(called_name)
            definition = next((item for item in functions if item.name == called_name), None)
            definition_line = _line_range(definition)[0] if definition is not None else call_line
            if function is None or function.kind != "workflow_entry":
                function = _find_or_add(
                    findings,
                    kind="workflow_entry",
                    name=called_name,
                    file_path=path,
                    start_line=definition_line,
                    end_line=_line_range(definition)[1] if definition is not None else call_line,
                    symbol_name=f"{called_name}:entry",
                    symbol_type="function",
                    framework=file_frameworks[0] if file_frameworks else None,
                    detection_method="AST __main__ guard analysis",
                    evidence_summary=f"The module invokes {called_name} from an __main__ guard.",
                    confidence="confirmed_syntax",
                    instrumentation_status="explicit_recommended" if not instrumentation_import else "already_configured",
                )
                function_findings[called_name] = function
            else:
                function.confidence = "confirmed_syntax"
                function.detection_method = "AST __main__ guard analysis"
                function.evidence_summary = f"The module invokes {called_name} from an __main__ guard."
            if definition is not None:
                node_owners[id(definition)] = function

    # Call, model, external-boundary, registration, and delegation relationships.
    for node in functions + classes:
        owner = node_owners.get(id(node))
        if owner is None:
            continue
        for call in _find_symbol_calls(node):
            line, _ = _line_range(call)
            called = _call_name(call)
            short_name = called.rsplit(".", 1)[-1]
            target = function_findings.get(short_name) or class_findings.get(short_name)
            if target and target.stable_id != owner.stable_id:
                _add_relationship(
                    relationships,
                    source=owner,
                    target=target,
                    target_name=target.name,
                    relationship_type="calls",
                    confidence="confirmed_syntax",
                    detection_method="AST call analysis",
                    evidence_summary=f"{owner.name} calls local symbol {target.name}.",
                    file_path=path,
                    line=line,
                )
            if _call_has_model_signal(called, imports):
                model = _find_or_add(
                    findings,
                    kind="model_call",
                    name=called,
                    file_path=path,
                    start_line=line,
                    end_line=line,
                    symbol_name=f"{owner.name}:{called}:{line}",
                    symbol_type="call",
                    framework=file_frameworks[0] if file_frameworks else None,
                    detection_method="AST model API call analysis",
                    evidence_summary=f"Call uses a model-like invocation API ({called}).",
                    confidence="confirmed_syntax",
                    instrumentation_status="supported_automatic" if instrumentation_import else "explicit_recommended",
                )
                _add_relationship(
                    relationships,
                    source=owner,
                    target=model,
                    target_name=model.name,
                    relationship_type="invokes",
                    confidence="confirmed_syntax",
                    detection_method="AST model API call analysis",
                    evidence_summary=f"{owner.name} contains the model invocation {called}.",
                    file_path=path,
                    line=line,
                )
            if _call_has_external_signal(called, imports):
                external = _find_or_add(
                    findings,
                    kind="external_service",
                    name=called,
                    file_path=path,
                    start_line=line,
                    end_line=line,
                    symbol_name=f"{owner.name}:{called}:{line}",
                    symbol_type="call",
                    framework=None,
                    detection_method="AST HTTP/client call analysis",
                    evidence_summary=f"Call reaches an external client boundary ({called}).",
                    confidence="confirmed_syntax",
                    instrumentation_status="needs_confirmation",
                )
                _add_relationship(
                    relationships,
                    source=owner,
                    target=external,
                    target_name=external.name,
                    relationship_type="uses_external_service",
                    confidence="confirmed_syntax",
                    detection_method="AST HTTP/client call analysis",
                    evidence_summary=f"{owner.name} uses {called}.",
                    file_path=path,
                    line=line,
                )
            if short_name.lower() in {"handoff", "delegate", "delegate_to", "transfer_to", "send_to"} or ".handoff" in called.lower():
                target_name = next((_literal_string(argument) for argument in call.args if _literal_string(argument)), None)
                delegate_target = function_findings.get(target_name or "") or class_findings.get(target_name or "")
                _add_relationship(
                    relationships,
                    source=owner,
                    target=delegate_target,
                    target_name=target_name or short_name,
                    relationship_type="delegates_to",
                    confidence="confirmed_syntax" if delegate_target or target_name else "unknown",
                    detection_method="AST delegation call analysis",
                    evidence_summary=f"{owner.name} uses a delegation/handoff call; the target is {'resolved' if delegate_target else 'not resolved from source' }.",
                    file_path=path,
                    line=line,
                )

            if short_name in {"add_node", "register", "register_tool", "add_tool"}:
                candidate_names = [_literal_string(argument) for argument in call.args]
                candidate_names = [name for name in candidate_names if name]
                for candidate_name in candidate_names:
                    registered = function_findings.get(candidate_name) or class_findings.get(candidate_name)
                    if registered:
                        _add_relationship(
                            relationships,
                            source=owner,
                            target=registered,
                            target_name=registered.name,
                            relationship_type="registers",
                            confidence="confirmed_syntax",
                            detection_method="AST registration call analysis",
                            evidence_summary=f"{owner.name} registers {registered.name}.",
                            file_path=path,
                            line=line,
                        )

            if short_name in {"add_edge", "add_conditional_edges"} and len(call.args) >= 2:
                from_name = _literal_string(call.args[0])
                to_name = _literal_string(call.args[1])
                graph = graph_findings[0] if graph_findings else owner
                target = function_findings.get(to_name or "") or class_findings.get(to_name or "")
                _add_relationship(
                    relationships,
                    source=graph,
                    target=target,
                    target_name=to_name,
                    relationship_type="routes_to",
                    confidence="confirmed_syntax" if target else "unknown",
                    detection_method="AST graph edge registration analysis",
                    evidence_summary=f"Graph registers an edge from {from_name or 'unknown'} to {to_name or 'unknown'}.",
                    file_path=path,
                    line=line,
                    metadata={"from_name": from_name, "to_name": to_name},
                )

    # Decorated tools can be registered outside a function body; retain a
    # conservative relationship when a known registration call names a symbol.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = _call_name(node).rsplit(".", 1)[-1]
        if called not in {"register_tool", "add_tool", "register"}:
            continue
        line, _ = _line_range(node)
        target_name = next((_literal_string(argument) for argument in node.args if _literal_string(argument)), None)
        target = function_findings.get(target_name or "")
        source = graph_findings[0] if graph_findings else next(iter(function_findings.values()), None)
        if source:
            _add_relationship(
                relationships,
                source=source,
                target=target,
                target_name=target_name,
                relationship_type="registers",
                confidence="confirmed_syntax" if target else "unknown",
                detection_method="AST registration call analysis",
                evidence_summary=f"Registration call names {target_name or 'an unresolved tool'}.",
                file_path=path,
                line=line,
            )
    return True


def analyze_repository(root: str | Path, settings: Settings) -> AnalysisResult:
    root_path = Path(root).resolve()
    files, limitations = _iter_source_files(root_path, settings)
    findings: dict[str, FindingData] = {}
    relationships: dict[tuple[str, str | None, str, int], RelationshipData] = {}
    frameworks: dict[str, dict[str, Any]] = {}
    language_counts: dict[str, int] = {}
    manifest_files: list[str] = []
    entry_candidates: list[dict[str, Any]] = []
    env_names: set[str] = set()
    parse_errors: list[str] = []
    python_files = 0

    for item in files:
        language = str(item["language"])
        language_counts[language] = language_counts.get(language, 0) + 1
        if item.get("manifest"):
            manifest_files.append(str(item["path"]))
        text = item.get("text")
        if not isinstance(text, str):
            continue
        if item.get("manifest"):
            for framework, line in _manifest_frameworks(str(item["path"]), text):
                frameworks.setdefault(framework, {"name": framework, "files": [], "evidence": []})
                if str(item["path"]) not in frameworks[framework]["files"]:
                    frameworks[framework]["files"].append(str(item["path"]))
                frameworks[framework]["evidence"].append(f"{item['path']}:{line} dependency manifest")
                _find_or_add(
                    findings,
                    kind="framework",
                    name=framework,
                    file_path=str(item["path"]),
                    start_line=line,
                    end_line=line,
                    symbol_name=framework.lower().replace(" ", "_") + ":manifest",
                    symbol_type="dependency",
                    framework=framework,
                    detection_method="dependency manifest analysis",
                    evidence_summary=f"Manifest names a dependency associated with {framework}.",
                    confidence="confirmed_syntax",
                    instrumentation_status=_framework_instrumentation(framework),
                )
        for match in ENV_NAME_RE.finditer(text):
            env_names.add(match.group(1) or match.group(2) or "")
        env_names.update(ENV_TEMPLATE_RE.findall(text))
        if language != "Python":
            # Inventory and framework markers are still useful for other
            # languages, but deep symbol discovery is intentionally Python-only.
            for marker, framework in (("opentelemetry", "OpenTelemetry"), ("langgraph", "LangGraph"), ("langchain", "LangChain")):
                if marker in text.lower():
                    frameworks.setdefault(framework, {"name": framework, "files": [], "evidence": []})
                    if str(item["path"]) not in frameworks[framework]["files"]:
                        frameworks[framework]["files"].append(str(item["path"]))
                    frameworks[framework]["evidence"].append(f"{item['path']}: text marker")
            continue
        python_files += 1
        if not _analyze_python_file(item, findings, relationships, frameworks):
            parse_errors.append(f"{item['path']}: {item.get('parse_error', 'parse failed')}")

    for finding in findings.values():
        if finding.kind == "workflow_entry":
            entry_candidates.append(
                {
                    "finding_id": finding.stable_id,
                    "name": finding.name,
                    "file_path": finding.file_path,
                    "start_line": finding.start_line,
                    "confidence": finding.confidence,
                    "reason": finding.evidence_summary,
                }
            )

    inventory = [
        {key: value for key, value in item.items() if key not in {"text"}}
        for item in files
    ]
    finding_counts: dict[str, int] = {}
    for finding in findings.values():
        finding_counts[finding.kind] = finding_counts.get(finding.kind, 0) + 1
    summary = {
        "files": inventory,
        "files_analyzed": sum(1 for item in files if "text" in item),
        "files_skipped": sum(1 for item in files if "text" not in item),
        "python_files_analyzed": python_files,
        "language_counts": language_counts,
        "manifest_files": sorted(manifest_files),
        "frameworks": sorted(frameworks.values(), key=lambda item: item["name"]),
        "entry_points": sorted(entry_candidates, key=lambda item: (item["file_path"], item["start_line"])),
        "finding_counts": finding_counts,
        "relationship_count": len(relationships),
        "environment_variable_names": sorted(name for name in env_names if name),
        "parse_errors": parse_errors,
        "coverage": {"Python": "deep_ast", "other_languages": "inventory_only"},
    }
    if python_files == 0 and any(language != "Other" for language in language_counts):
        limitations.append("Only inventory-level analysis is available for non-Python source files.")
    limitations.append("Static findings describe source evidence; runtime behavior and execution paths are not proven.")
    limitations.append("Repository files, tests, dependencies, and entry points were not executed or imported.")
    return AnalysisResult(
        findings=sorted(findings.values(), key=lambda item: (item.file_path, item.start_line, item.kind, item.name)),
        relationships=sorted(relationships.values(), key=lambda item: (item.file_path, item.start_line, item.relationship_type)),
        summary=summary,
        limitations=sorted(set(limitations)),
        partially_analyzed=bool(parse_errors or summary["files_skipped"]),
    )


def config_for_analysis(
    *,
    project: Any,
    analysis: Any,
    findings: list[Any],
    selection: Any,
    adapters: list[dict[str, Any]],
) -> dict[str, Any]:
    if selection.schema_version != "1.0":
        raise ValueError("Only instrumentation configuration schema version 1.0 is supported")
    by_id = {finding.stable_id: finding for finding in findings}
    workflow_ids = list(dict.fromkeys(selection.workflow_entry_point_ids))
    component_ids = list(dict.fromkeys(selection.component_ids))
    unknown = [identifier for identifier in workflow_ids + component_ids if identifier not in by_id]
    if unknown:
        raise ValueError(f"Unknown discovery finding: {unknown[0]}")
    invalid_workflows = [identifier for identifier in workflow_ids if by_id[identifier].kind != "workflow_entry"]
    if invalid_workflows:
        raise ValueError("workflow_entry_point_ids must reference workflow_entry findings")
    invalid_components = [
        identifier
        for identifier in component_ids
        if by_id[identifier].kind in {"workflow_entry", "framework", "instrumentation"}
    ]
    if invalid_components:
        raise ValueError("component_ids must reference instrumentable discovery components")
    if len(selection.excluded_paths) != len(set(selection.excluded_paths)):
        raise ValueError("excluded_paths must not contain duplicates")
    for excluded_path in selection.excluded_paths:
        normalized = excluded_path.replace("\\", "/")
        parts = [part for part in normalized.split("/") if part not in {"", "."}]
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or ".." in parts:
            raise ValueError("excluded_paths must stay within the repository")
    selected = [by_id[identifier] for identifier in workflow_ids + component_ids]
    requested_adapters = list(dict.fromkeys(selection.adapter_ids))
    known_adapter_ids = {str(adapter["id"]) for adapter in adapters}
    unknown_adapters = [identifier for identifier in requested_adapters if identifier not in known_adapter_ids]
    if unknown_adapters:
        raise ValueError(f"Unknown instrumentation adapter: {unknown_adapters[0]}")
    selected_adapters = [adapter for adapter in adapters if adapter["id"] in set(requested_adapters)]
    config = {
        "schema_version": selection.schema_version,
        "project": {"id": project.id, "name": project.name},
        "source": {
            "analysis_id": analysis.id,
            "source_kind": analysis.source_kind,
            "source_url": analysis.source_url,
            "branch": analysis.branch,
            "commit_sha": analysis.commit_sha,
            "source_revision": analysis.source_revision,
            "archive_fingerprint": analysis.archive_fingerprint,
        },
        "workflow_entry_points": [
            {
                "finding_id": finding.stable_id,
                "name": finding.name,
                "file_path": finding.file_path,
                "start_line": finding.start_line,
                "end_line": finding.end_line,
            }
            for finding in selected
            if finding.kind == "workflow_entry"
        ],
        "components": [
            {
                "finding_id": finding.stable_id,
                "kind": finding.kind,
                "name": finding.name,
                "file_path": finding.file_path,
                "start_line": finding.start_line,
                "end_line": finding.end_line,
                "framework": finding.framework,
                "instrumentation_status": finding.instrumentation_status,
            }
            for finding in selected
            if finding.kind != "workflow_entry"
        ],
        "adapters": selected_adapters,
        "instrumentation": {
            "capture_payloads": bool(selection.capture_payloads),
            "redact_secrets": bool(selection.redact_secrets),
        },
        "exclusions": {"paths": sorted(set(selection.excluded_paths))},
        "limitations": list(analysis.limitations_json or []),
        "notes": selection.notes,
    }
    # Validate the generated document before it can be persisted. The final
    # round-trip also guarantees deterministic JSON-compatible values and keeps
    # credentials/source objects out of the saved representation.
    validated = InstrumentationConfigDocument.model_validate(config).model_dump(mode="json")
    return json.loads(json.dumps(validated, sort_keys=True))
