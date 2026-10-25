"""Compatibility package for the SpanTrace Python SDK.

The original Task 1 import path was ``agentscope``. It remains supported while
new integrations and documentation use the ``spantrace`` package name.
"""

from .client import AgentScope, Span, SpanTrace, Trace

__all__ = ["AgentScope", "SpanTrace", "Span", "Trace"]
__version__ = "0.1.0"
