from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from resolving.containerization.runtime.adapter_runtime import (
    AdapterMetadata,
    emit_payload,
    error_response,
    handle_common_command,
    load_request_from_stdin,
    success_response,
)


ADAPTER_NAME = os.getenv("RESOLVER_NAME", "npm-dependency-resolver")
ADAPTER_VERSION = os.getenv("ADAPTER_VERSION", "container-v1")
BACKEND_VERSION = os.getenv("BACKEND_VERSION", "legacy-cpp")
BACKEND_BINARY = Path(os.getenv("NPM_BACKEND_BINARY", "/usr/local/bin/npm-resolver"))
PLATFORM = {
    "os": os.getenv("NPM_PLATFORM_OS", "linux"),
    "cpu": os.getenv("NPM_PLATFORM_CPU", "x64"),
    "libc": os.getenv("NPM_PLATFORM_LIBC", "glibc"),
}
PROGRESS_PREFIXES = ("Resolving:", "正在检测:")
STATE_MAP = {
    "Ok": "ok",
    "Conflict": "conflict",
    "Empty": "empty",
    "QueueLoop": "queue_loop",
    "QueueLoopReplacementDetected": "queue_loop_replacement_detected",
    "LoadLoop": "load_loop",
    "PlaceLoop": "place_loop",
    "NpmError": "npm_error",
    "UnknownError": "unknown_error",
}
METADATA = AdapterMetadata(
    name=ADAPTER_NAME,
    adapter_version=ADAPTER_VERSION,
    backend_version=BACKEND_VERSION,
    ecosystem="npm",
)


def _package_id(name: str, version: str | None) -> str:
    return f"npm:{name}@{version}" if version else f"npm:{name}"


def _parse_dependency_label(label: str) -> dict[str, Any]:
    peer = False
    coordinate = label
    if coordinate.endswith(" (peer)"):
        coordinate = coordinate[: -len(" (peer)")]
        peer = True

    alias_target: str | None = None
    if "@npm:" in coordinate:
        dependency_name, alias_spec = coordinate.split("@npm:", 1)
        alias_target, version = alias_spec.rsplit("@", 1)
    else:
        dependency_name, version = coordinate.rsplit("@", 1)

    return {
        "name": dependency_name,
        "version": version,
        "peer": peer,
        "alias_target": alias_target,
    }


def _parse_directory_entry(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or " " not in stripped:
        return None
    path_text, version = stripped.rsplit(" ", 1)
    if not path_text or not version:
        return None
    return path_text, version


def _collect_directory_metadata(directory_tree: list[Any]) -> tuple[str | None, dict[str, list[str]]]:
    root_version: str | None = None
    install_paths: dict[str, set[str]] = {}

    for entry in directory_tree:
        if not isinstance(entry, str):
            continue
        parsed = _parse_directory_entry(entry)
        if parsed is None:
            continue

        path_text, version = parsed
        if path_text == ".":
            root_version = version
            continue
        if "/node_modules/" not in path_text:
            continue

        package_name = path_text.rsplit("/node_modules/", 1)[-1]
        node_id = _package_id(package_name, version)
        install_paths.setdefault(node_id, set()).add(path_text)

    normalized_paths = {node_id: sorted(paths) for node_id, paths in install_paths.items()}
    return root_version, normalized_paths


def _build_node(
    name: str,
    version: str | None,
    scope: str,
    *,
    install_paths: list[str] | None = None,
    alias_target: str | None = None,
) -> dict[str, Any]:
    attributes: dict[str, Any] = {"optional": False, "peer": False, "dev": False}
    if install_paths:
        attributes["install_paths"] = install_paths
    if alias_target:
        attributes["alias_target"] = alias_target

    return {
        "id": _package_id(name, version),
        "ecosystem": "npm",
        "name": name,
        "version": version,
        "labels": {"scope": scope},
        "attributes": attributes,
    }


def normalize_backend_result(result: dict[str, Any]) -> dict[str, Any]:
    if all(key in result for key in ("root", "nodes", "edges")):
        return result

    package = result.get("package")
    if not isinstance(package, dict):
        raise ValueError("npm backend response is missing package metadata")

    package_name = package.get("name")
    if not isinstance(package_name, str) or not package_name.strip():
        raise ValueError("npm backend response is missing package.name")

    directory_tree = result.get("directory_tree")
    if directory_tree is None:
        directory_tree = []
    if not isinstance(directory_tree, list):
        raise ValueError("npm backend response field directory_tree must be a list")

    dependency_tree = result.get("dependency_tree")
    if dependency_tree is None:
        dependency_tree = {}
    if not isinstance(dependency_tree, dict):
        raise ValueError("npm backend response field dependency_tree must be an object or null")

    root_version, install_paths_by_id = _collect_directory_metadata(directory_tree)
    resolved_root_version = root_version or package.get("version")
    root_node = _build_node(package_name, resolved_root_version, "root", install_paths=["."])

    nodes_by_id: dict[str, dict[str, Any]] = {root_node["id"]: root_node}
    edges: list[dict[str, Any]] = []
    edge_keys: set[tuple[Any, ...]] = set()

    def ensure_node(name: str, version: str | None, alias_target: str | None) -> dict[str, Any]:
        node_id = _package_id(name, version)
        install_paths = install_paths_by_id.get(node_id)
        if node_id not in nodes_by_id:
            nodes_by_id[node_id] = _build_node(
                name,
                version,
                "runtime",
                install_paths=install_paths,
                alias_target=alias_target,
            )
        else:
            attributes = nodes_by_id[node_id].setdefault("attributes", {})
            if install_paths:
                attributes["install_paths"] = install_paths
            if alias_target and not attributes.get("alias_target"):
                attributes["alias_target"] = alias_target
        return nodes_by_id[node_id]

    def add_edge(
        source_id: str,
        target_id: str,
        depth: int,
        peer: bool,
        deduped: bool,
        alias_target: str | None,
    ) -> None:
        key = (source_id, target_id, depth, peer, deduped, alias_target)
        if key in edge_keys:
            return
        edge_keys.add(key)

        attributes: dict[str, Any] = {"optional": False, "peer": peer, "replaced": False}
        if deduped:
            attributes["deduped"] = True
        if alias_target:
            attributes["alias_target"] = alias_target

        edges.append(
            {
                "from": source_id,
                "to": target_id,
                "type": "direct" if depth == 1 else "transitive",
                "constraint": None,
                "depth": depth,
                "attributes": attributes,
            }
        )

    def walk(parent_id: str, subtree: dict[str, Any], depth: int) -> None:
        for label, child in subtree.items():
            if not isinstance(label, str):
                raise ValueError("npm backend dependency_tree keys must be strings")

            try:
                parsed = _parse_dependency_label(label)
            except ValueError as exc:
                raise ValueError(f"invalid npm dependency label: {label}") from exc

            node = ensure_node(parsed["name"], parsed["version"], parsed["alias_target"])
            deduped = child == "deduped"
            add_edge(parent_id, node["id"], depth, parsed["peer"], deduped, parsed["alias_target"])

            if isinstance(child, dict):
                walk(node["id"], child, depth + 1)
            elif child in {None, "deduped"}:
                continue
            else:
                raise ValueError(
                    f"npm backend dependency_tree entry for {label} must be an object, null, or 'deduped'"
                )

    walk(root_node["id"], dependency_tree, 1)

    backend_metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    metrics = dict(backend_metrics)
    metrics["node_count"] = len(nodes_by_id)
    metrics["edge_count"] = len(edges)
    metrics.setdefault("directory_entry_count", len(directory_tree))

    backend_semantics = result.get("semantics") if isinstance(result.get("semantics"), dict) else {}
    semantics = dict(backend_semantics)
    semantics["resolution"] = result.get("resolution")
    semantics["requested_version"] = package.get("version")
    semantics["version_spec"] = package.get("version_spec")
    semantics["resolved_root_version"] = resolved_root_version
    semantics["directory_tree"] = directory_tree
    if "replacement_record" in result:
        semantics["replacement_record"] = result["replacement_record"]

    return {
        "root": root_node,
        "nodes": list(nodes_by_id.values()),
        "edges": edges,
        "semantics": semantics,
        "metrics": metrics,
    }


def build_capabilities() -> dict[str, Any]:
    return {
        "commands": ["resolve", "health", "capabilities"],
        "formats": ["graph"],
        "features": ["raw", "peer-dependencies", "directory-tree"],
        "platform": False,
    }


def check_health() -> dict[str, Any]:
    backend_ready = BACKEND_BINARY.exists()
    checks = [
        {
            "name": "backend_binary",
            "status": "ok" if backend_ready else "error",
            "details": str(BACKEND_BINARY) if backend_ready else f"missing backend binary: {BACKEND_BINARY}",
        },
        {
            "name": "registry_source",
            "status": "ok",
            "details": "compiled configuration targets the official npm registry",
        },
        {
            "name": "platform_profile",
            "status": "ok",
            "details": f"os={PLATFORM['os']} cpu={PLATFORM['cpu']} libc={PLATFORM['libc']}",
        },
    ]
    state = "ok" if all(check["status"] == "ok" for check in checks) else "degraded"
    return {"state": state, "checks": checks}


def _parse_resolution_log(log_line: str) -> tuple[str, str | None]:
    if ": " not in log_line:
        raise ValueError("npm backend resolution log is malformed")

    _, status_payload = log_line.split(": ", 1)
    state_text, separator, trailing_text = status_payload.partition(": ")
    normalized_state = STATE_MAP.get(state_text)
    if normalized_state is None:
        raise ValueError(f"unsupported npm backend resolution state: {state_text}")
    replacement_record = trailing_text if separator and trailing_text else None
    return normalized_state, replacement_record


def _unwrap_root_dependency_tree(
    dependency_tree: dict[str, Any], package_name: str, package_version: str
) -> dict[str, Any]:
    if len(dependency_tree) != 1:
        return dependency_tree

    only_label, only_child = next(iter(dependency_tree.items()))
    if not isinstance(only_label, str) or not isinstance(only_child, dict):
        return dependency_tree

    try:
        parsed = _parse_dependency_label(only_label)
    except ValueError:
        return dependency_tree

    if (
        parsed["name"] == package_name
        and parsed["version"] == package_version
        and not parsed["peer"]
        and parsed["alias_target"] is None
    ):
        return only_child
    return dependency_tree


def _parse_backend_stdout(stdout_text: str, package_name: str, package_version: str) -> dict[str, Any]:
    stripped_text = stdout_text.strip()
    if not stripped_text:
        raise ValueError("npm backend emitted empty stdout")

    lines = stdout_text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        raise ValueError("npm backend emitted empty stdout")

    progress_line = lines.pop(0).strip()
    if not any(progress_line.startswith(prefix) for prefix in PROGRESS_PREFIXES):
        raise ValueError("npm backend missing progress prefix")

    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise ValueError("npm backend output is missing resolution log")

    log_line = lines.pop().strip()
    dependency_tree: dict[str, Any] = {}
    dependency_line = lines.pop(0).strip() if lines else ""
    if dependency_line:
        try:
            parsed_dependency_tree = json.loads(dependency_line)
        except json.JSONDecodeError as exc:
            raise ValueError("npm backend dependency tree is not valid JSON") from exc
        if not isinstance(parsed_dependency_tree, dict):
            raise ValueError("npm backend dependency tree must be a JSON object")
        dependency_tree = _unwrap_root_dependency_tree(parsed_dependency_tree, package_name, package_version)

    directory_tree = [line.rstrip() for line in lines if line.strip()]
    resolution_state, replacement_record = _parse_resolution_log(log_line)

    metrics = {
        "directory_entry_count": len(directory_tree),
    }
    semantics: dict[str, Any] = {
        "source": "containerized-npm-resolver",
        "platform": dict(PLATFORM),
    }
    if replacement_record:
        semantics["replacement_record"] = replacement_record

    result: dict[str, Any] = {
        "package": {
            "name": package_name,
            "version": package_version,
            "version_spec": package_version,
        },
        "resolution": {
            "state": resolution_state,
            "message": log_line,
        },
        "dependency_tree": dependency_tree,
        "directory_tree": directory_tree,
        "metrics": metrics,
        "semantics": semantics,
    }
    if replacement_record:
        result["replacement_record"] = replacement_record
    return result


def _map_backend_state(package_version: str | None, result: dict[str, Any], raw: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any] | None]:
    resolution = result.get("resolution") if isinstance(result, dict) else None
    if not isinstance(resolution, dict):
        return None, raw, {
            "code": "PROTOCOL_ERROR",
            "message": "npm backend response is missing resolution metadata",
            "backend_error": None,
            "retryable": False,
        }

    state = resolution.get("state")
    message = resolution.get("message") or f"npm resolution finished with state: {state}"
    if state == "ok":
        return result, raw, None
    if state == "conflict":
        return None, raw, {
            "code": "RESOLUTION_CONFLICT",
            "message": message,
            "backend_error": state,
            "retryable": False,
        }
    if state == "empty":
        return None, raw, {
            "code": "VERSION_NOT_FOUND" if package_version else "PACKAGE_NOT_FOUND",
            "message": message,
            "backend_error": state,
            "retryable": False,
        }
    if state == "npm_error":
        return None, raw, {
            "code": "DATA_SOURCE_UNAVAILABLE",
            "message": message,
            "backend_error": state,
            "retryable": True,
        }

    return None, raw, {
        "code": "INTERNAL_ERROR",
        "message": message,
        "backend_error": state,
        "retryable": False,
    }


def run_backend(package_name: str, package_version: str | None, timeout_ms: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    if not package_version:
        return None, None, {
            "code": "INVALID_ARGUMENT",
            "message": "package.version is required for npm resolve",
            "backend_error": None,
            "retryable": False,
        }

    if not BACKEND_BINARY.exists():
        return None, None, {
            "code": "BACKEND_MISCONFIGURED",
            "message": f"npm backend binary was not found at {BACKEND_BINARY}",
            "backend_error": None,
            "retryable": False,
        }

    command = [str(BACKEND_BINARY), package_name, package_version]
    backend_start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=timeout_ms / 1000,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return None, {
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "exit_code": None,
        }, {
            "code": "TIMEOUT",
            "message": f"npm backend timed out after {timeout_ms}ms",
            "backend_error": None,
            "retryable": True,
        }
    except OSError as exc:
        return None, None, {
            "code": "BACKEND_MISCONFIGURED",
            "message": "failed to start npm backend binary",
            "backend_error": str(exc),
            "retryable": False,
        }

    backend_duration_ms = int((time.perf_counter() - backend_start) * 1000)
    raw = {
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": completed.returncode,
    }
    if completed.returncode != 0:
        backend_error = completed.stderr.strip() or None
        return None, raw, {
            "code": "BACKEND_CRASHED",
            "message": backend_error or "npm backend exited with non-zero status",
            "backend_error": "CppProcessError",
            "retryable": False,
        }

    try:
        parsed_result = _parse_backend_stdout(completed.stdout, package_name, package_version)
    except ValueError as exc:
        return None, raw, {
            "code": "PROTOCOL_ERROR",
            "message": str(exc),
            "backend_error": exc.__class__.__name__,
            "retryable": False,
        }

    parsed_metrics = parsed_result.get("metrics") if isinstance(parsed_result.get("metrics"), dict) else {}
    parsed_metrics = dict(parsed_metrics)
    parsed_metrics.setdefault("duration_ms", backend_duration_ms)
    parsed_result["metrics"] = parsed_metrics
    raw["backend_payload"] = parsed_result

    mapped_result, raw, error = _map_backend_state(package_version, parsed_result, raw)
    if error or mapped_result is None:
        return None, raw, error

    try:
        normalized_result = normalize_backend_result(mapped_result)
    except ValueError as exc:
        return None, raw, {
            "code": "PROTOCOL_ERROR",
            "message": str(exc),
            "backend_error": exc.__class__.__name__,
            "retryable": False,
        }

    return normalized_result, raw, None


def main() -> int:
    start_time = time.perf_counter()
    request, request_error = load_request_from_stdin(METADATA, start_time)
    if request_error is not None:
        emit_payload(request_error)
        return 1

    common_response = handle_common_command(request, METADATA, start_time, build_capabilities, check_health)
    if common_response is not None:
        exit_code, payload = common_response
        emit_payload(payload)
        return exit_code

    package = request["package"]
    timeout_ms = request.get("options", {}).get("timeout_ms", 180000)
    result, raw, error = run_backend(package["name"], package.get("version"), timeout_ms)
    if error:
        emit_payload(
            error_response(
                request,
                METADATA,
                error["code"],
                error["message"],
                error.get("backend_error"),
                error["retryable"],
                start_time,
                raw=raw,
            )
        )
        return 1

    emit_payload(success_response(request, METADATA, result, start_time, raw=raw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
