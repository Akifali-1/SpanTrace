"""Fixed launch wrapper used only inside the restricted execution container."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import nullcontext
import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path, PurePosixPath
from typing import Any


def _load_callable(root: Path, relative_file: str, symbol: str):
    relative = PurePosixPath(relative_file)
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts) or relative.suffix != ".py":
        raise ValueError("Invalid Python entry path")
    source = (root.joinpath(*relative.parts)).resolve()
    source.relative_to(root.resolve())
    if not source.is_file():
        raise FileNotFoundError(relative_file)
    if not symbol.isidentifier():
        raise ValueError("Entry symbol must be a simple Python identifier")
    module_name = f"spantrace_entry_{source.stem}_{os.getpid()}"
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise ImportError("Could not load the selected workflow source")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(root))
    spec.loader.exec_module(module)
    function = getattr(module, symbol, None)
    if not callable(function):
        raise TypeError(f"Selected entry symbol is not callable: {symbol}")
    return function


def _invoke(function: Any, inputs: dict[str, Any]) -> Any:
    signature = inspect.signature(function)
    required = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in {parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD}
        and parameter.default is parameter.empty
    ]
    if not required:
        value = function()
    else:
        value = function(inputs)
    return asyncio.run(value) if inspect.isawaitable(value) else value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--entry-file", required=True)
    parser.add_argument("--entry-symbol", required=True)
    args = parser.parse_args()
    root = Path(args.source_root).resolve()
    inputs = json.loads(os.environ.get("SPANTRACE_EXECUTION_INPUT", "{}"))
    if not isinstance(inputs, dict):
        raise ValueError("Execution input must be a JSON object")

    # The selected Task 2 adapter is applied inside the worker. The token is a
    # short-lived run-scoped capability, not a project API key.
    from spantrace import SpanTrace

    scope = SpanTrace.from_env()
    adapter = os.environ.get("SPANTRACE_EXECUTION_ADAPTER", "manual")
    provider = None
    otel_parent = nullcontext()
    if adapter == "opentelemetry":
        provider, _ = scope.instrument_opentelemetry(service_name="spantrace-controlled-workflow", framework="spantrace-execution")
        from opentelemetry import trace as otel_trace
        from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, TraceState, use_span

        otel_trace.set_tracer_provider(provider)
        trace_id = os.environ.get("SPANTRACE_TRACE_ID", "")
        if len(trace_id) != 32 or not all(character in "0123456789abcdef" for character in trace_id.lower()):
            raise ValueError("Execution trace ID must be a 32-character hexadecimal value")
        parent_context = SpanContext(
            trace_id=int(trace_id, 16),
            span_id=int(os.urandom(8).hex(), 16),
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
            trace_state=TraceState(),
        )
        otel_parent = use_span(NonRecordingSpan(parent_context), end_on_exit=False)

    try:
        function = _load_callable(root, args.entry_file, args.entry_symbol)
        with otel_parent:
            with scope.trace(args.entry_symbol, metadata={"execution": True, "source_file": args.entry_file}) as trace:
                with trace.span(args.entry_symbol, kind="agent", input=inputs) as span:
                    result = _invoke(function, inputs)
                    span.set_output(result)
    finally:
        if provider is not None:
            provider.shutdown()
    print("SPANTRACE_RESULT=" + json.dumps({"output": result}, default=str, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"SPANTRACE_WORKER_ERROR={type(error).__name__}: {error}", flush=True)
        raise
