from __future__ import annotations

from typing import Any


def ensure_graph_result(result: dict[str, Any], ecosystem: str) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError(f"{ecosystem} backend response must be a JSON object")

    missing = [key for key in ("root", "nodes", "edges") if key not in result]
    if missing:
        raise ValueError(
            f"{ecosystem} backend response must include graph fields: {', '.join(missing)}"
        )

    root = result.get("root")
    nodes = result.get("nodes")
    edges = result.get("edges")
    if not isinstance(root, dict):
        raise ValueError(f"{ecosystem} backend response field root must be an object")
    if not isinstance(nodes, list):
        raise ValueError(f"{ecosystem} backend response field nodes must be a list")
    if not isinstance(edges, list):
        raise ValueError(f"{ecosystem} backend response field edges must be a list")

    normalized = dict(result)
    semantics = result.get("semantics")
    normalized["semantics"] = dict(semantics) if isinstance(semantics, dict) else {}

    metrics = result.get("metrics")
    normalized_metrics = dict(metrics) if isinstance(metrics, dict) else {}
    normalized_metrics.setdefault("node_count", len(nodes))
    normalized_metrics.setdefault("edge_count", len(edges))
    normalized["metrics"] = normalized_metrics
    return normalized
