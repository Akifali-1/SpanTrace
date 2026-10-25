"""Small, failure-tolerant Python SDK for AgentScope trace capture."""

from .client import AgentScope, Span, Trace

__all__ = ["AgentScope", "Span", "Trace"]
__version__ = "0.1.0"
