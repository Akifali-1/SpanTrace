"""Compatibility re-exports for ``spantrace.client``."""

from agentscope.client import AgentScope, Span, SpanTrace, Trace, default_redactor

__all__ = ["AgentScope", "SpanTrace", "Span", "Trace", "default_redactor"]
