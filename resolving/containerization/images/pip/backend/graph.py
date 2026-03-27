from __future__ import annotations

from collections import deque
from typing import Any

try:
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    from packaging.version import InvalidVersion, Version
except ImportError:  # pragma: no cover - fallback for minimal pip environments
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name
    from pip._vendor.packaging.version import InvalidVersion, Version


def _package_id(name: str, version: str | None) -> str:
    return f"pip:{canonicalize_name(name)}@{version}" if version else f"pip:{canonicalize_name(name)}"


def _sort_version_text(version: str | None) -> tuple[int, object]:
    if version is None:
        return (0, "")
    try:
        return (1, Version(version))
    except InvalidVersion:
        return (0, version)


def _graph_forwards(resolution_result: Any) -> dict[Any, set[Any]]:
    graph = getattr(resolution_result, "graph", None)
    if graph is None:
        raise ValueError("resolution result is missing graph")
    forwards = getattr(graph, "_forwards", None)
    if not isinstance(forwards, dict):
        raise ValueError("resolution graph does not expose forwards map")
    return forwards


def _graph_vertices(resolution_result: Any) -> set[Any]:
    graph = getattr(resolution_result, "graph", None)
    if graph is None:
        raise ValueError("resolution result is missing graph")
    vertices = getattr(graph, "_vertices", None)
    if not isinstance(vertices, set):
        raise ValueError("resolution graph does not expose vertex set")
    return vertices


def _build_depths(forwards: dict[Any, set[Any]], root_identifiers: list[Any]) -> dict[Any, int]:
    depths: dict[Any, int] = {}
    queue: deque[tuple[Any, int]] = deque((identifier, 0) for identifier in root_identifiers)
    while queue:
        identifier, depth = queue.popleft()
        if identifier in depths and depths[identifier] <= depth:
            continue
        depths[identifier] = depth
        for child in forwards.get(identifier, set()):
            queue.append((child, depth + 1))
    return depths


def _edge_constraint(parent_candidate: Any, child_candidate: Any) -> str | None:
    parent_dependencies = getattr(parent_candidate, "dependencies", ())
    child_name = canonicalize_name(getattr(child_candidate, "name", ""))
    matching: list[str] = []
    for dependency in parent_dependencies:
        if not isinstance(dependency, Requirement):
            continue
        if canonicalize_name(dependency.name) != child_name:
            continue
        if str(dependency):
            matching.append(str(dependency))
    if not matching:
        return None
    return " || ".join(sorted(set(matching)))


def build_graph_result(
    *,
    package_name: str,
    requested_version: str | None,
    resolution_result: Any,
    metadata_mode: str,
) -> dict[str, Any]:
    mapping = getattr(resolution_result, "mapping", None)
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("resolution result is missing candidate mapping")

    forwards = _graph_forwards(resolution_result)
    vertices = _graph_vertices(resolution_result)
    root_identifiers = sorted(forwards.get(None, set()), key=str)
    if not root_identifiers:
        raise ValueError("resolution graph did not contain root dependencies")

    root_identifier = root_identifiers[0]
    root_candidate = mapping.get(root_identifier)
    if root_candidate is None:
        raise ValueError("root candidate is missing from resolution mapping")

    root_node_id = _package_id(root_candidate.name, root_candidate.version)
    depths = _build_depths(forwards, root_identifiers)

    nodes_by_id: dict[str, dict[str, Any]] = {}
    identifier_to_node_id: dict[Any, str] = {}

    sorted_vertices = sorted(
        (identifier for identifier in vertices if identifier is not None and identifier in mapping),
        key=lambda identifier: (
            depths.get(identifier, 9999),
            canonicalize_name(getattr(mapping[identifier], "name", str(identifier))),
            _sort_version_text(getattr(mapping[identifier], "version", None)),
        ),
    )

    for identifier in sorted_vertices:
        candidate = mapping[identifier]
        node_id = _package_id(candidate.name, candidate.version)
        identifier_to_node_id[identifier] = node_id
        node_scope = "root" if identifier == root_identifier else "runtime"
        candidate_extras = sorted(set(getattr(candidate, "extras", ())))
        attributes: dict[str, Any] = {
            "optional": False,
            "peer": False,
            "dev": False,
            "yanked": bool(getattr(candidate, "yanked", False)),
            "source_kind": getattr(candidate, "source_kind", None),
        }
        if getattr(candidate, "requires_python", None):
            attributes["requires_python"] = candidate.requires_python
        if candidate_extras:
            attributes["extras"] = candidate_extras

        if node_id not in nodes_by_id:
            nodes_by_id[node_id] = {
                "id": node_id,
                "ecosystem": "pip",
                "name": canonicalize_name(candidate.name),
                "version": candidate.version,
                "labels": {"scope": node_scope},
                "attributes": attributes,
            }
            continue

        existing = nodes_by_id[node_id]
        if node_scope == "root":
            existing["labels"] = {"scope": "root"}
        existing_attributes = existing.setdefault("attributes", {})
        if candidate_extras:
            merged = sorted(set(existing_attributes.get("extras", [])) | set(candidate_extras))
            existing_attributes["extras"] = merged

    edges: list[dict[str, Any]] = []
    edge_keys: set[tuple[str, str, str | None]] = set()
    for parent_identifier, children in forwards.items():
        if parent_identifier is None:
            continue
        parent_candidate = mapping.get(parent_identifier)
        parent_node_id = identifier_to_node_id.get(parent_identifier)
        if parent_candidate is None or parent_node_id is None:
            continue

        for child_identifier in sorted(children, key=str):
            child_candidate = mapping.get(child_identifier)
            child_node_id = identifier_to_node_id.get(child_identifier)
            if child_candidate is None or child_node_id is None:
                continue
            if parent_node_id == child_node_id:
                continue

            constraint = _edge_constraint(parent_candidate, child_candidate)
            edge_key = (parent_node_id, child_node_id, constraint)
            if edge_key in edge_keys:
                continue
            edge_keys.add(edge_key)

            child_depth = depths.get(child_identifier, 1)
            edges.append(
                {
                    "from": parent_node_id,
                    "to": child_node_id,
                    "type": "direct" if child_depth == 1 else "transitive",
                    "constraint": constraint,
                    "depth": child_depth,
                    "attributes": {
                        "optional": False,
                        "peer": False,
                        "replaced": False,
                    },
                }
            )

    root_node = {
        "id": root_node_id,
        "ecosystem": "pip",
        "name": canonicalize_name(root_candidate.name),
        "version": root_candidate.version,
    }
    semantics = {
        "source": "resolvelib",
        "metadata_mode": metadata_mode,
        "requested_package": package_name,
        "requested_version": requested_version,
        "resolved_root_version": root_candidate.version,
        "root_identifier": str(root_identifier),
        "root_requires_python": getattr(root_candidate, "requires_python", None),
    }
    metrics = {
        "node_count": len(nodes_by_id),
        "edge_count": len(edges),
        "direct_dependency_count": len(forwards.get(root_identifier, set())),
    }
    return {
        "root": root_node,
        "nodes": list(nodes_by_id.values()),
        "edges": edges,
        "semantics": semantics,
        "metrics": metrics,
    }
