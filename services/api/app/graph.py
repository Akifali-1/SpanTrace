from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


def _event_node(event: Any) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "span_id": event.span_id,
        "parent_span_id": event.parent_span_id,
        "label": event.agent_name or event.tool_name or event.model_name or event.event_type,
        "event_type": event.event_type,
        "kind": event.kind,
        "status": event.status,
        "occurred_at": event.occurred_at.isoformat() + "Z",
        "integration": event.integration,
        "framework": event.framework,
        "relationship": event.relationship,
        "relationship_confidence": event.relationship_confidence,
        "handoff_to": event.handoff_to,
    }


def build_execution_graph(events: Iterable[Any]) -> dict[str, Any]:
    """Build a conservative graph from observed IDs and explicit handoffs.

    Parent edges are only created when the parent span ID is present in the
    same trace. Handoffs without a target span ID remain unresolved rather than
    being guessed from temporal proximity.
    """
    ordered = sorted(events, key=lambda item: item.occurred_at)
    nodes = [_event_node(event) for event in ordered]
    span_nodes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        if node["span_id"]:
            span_nodes[node["span_id"]].append(node)

    edges: list[dict[str, Any]] = []
    unresolved_parents = 0
    unresolved_handoffs = 0
    for event, node in zip(ordered, nodes):
        if event.parent_span_id:
            parents = span_nodes.get(event.parent_span_id, [])
            if parents:
                # Lifecycle events can reuse the root span ID. Link children to
                # the first observed root node instead of making run_completed
                # appear to be their parent.
                edges.append({"from": parents[0]["event_id"], "to": node["event_id"], "type": "parent", "confidence": "observed"})
            else:
                unresolved_parents += 1
                edges.append({"from": event.parent_span_id, "to": node["event_id"], "type": "missing_parent", "confidence": "unknown"})

        if event.event_type == "handoff" or event.handoff_to:
            metadata = event.metadata_json or {}
            target_span_id = metadata.get("target_span_id") if isinstance(metadata, dict) else None
            target = span_nodes.get(target_span_id, []) if target_span_id else []
            if target:
                edges.append({"from": node["event_id"], "to": target[0]["event_id"], "type": "handoff", "confidence": event.relationship_confidence})
            else:
                unresolved_handoffs += 1
                edges.append({"from": node["event_id"], "to": None, "target": event.handoff_to, "type": "handoff", "confidence": event.relationship_confidence or "unknown"})

    root_events = [node for node in nodes if node["event_type"] == "run_started"]
    has_completion = any(node["event_type"] == "run_completed" for node in nodes)
    unknown_relationships = sum(1 for node in nodes if node["relationship_confidence"] in {"unknown", "inferred"})
    partial = not root_events or not has_completion or unresolved_parents > 0
    return {
        "nodes": nodes,
        "edges": edges,
        "root_event_id": root_events[0]["event_id"] if root_events else None,
        "status": "partially_observed" if partial or unresolved_handoffs or unknown_relationships else "observed",
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "unresolved_parent_count": unresolved_parents,
            "unresolved_handoff_count": unresolved_handoffs,
            "uncertain_relationship_count": unknown_relationships,
            "has_root": bool(root_events),
            "has_completion": has_completion,
        },
    }
