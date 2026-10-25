"""Canonical SpanTrace SDK import path."""

from agentscope import AgentScope, Span, SpanTrace, Trace
from agentscope.integrations import CallbackAdapter, OpenTelemetryAdapter

__all__ = ["SpanTrace", "AgentScope", "Span", "Trace", "CallbackAdapter", "OpenTelemetryAdapter"]
__version__ = "0.2.0"
