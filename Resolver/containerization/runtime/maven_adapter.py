from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from Resolver.containerization.runtime.adapter_runtime import (
    AdapterMetadata,
    emit_payload,
    error_response,
    handle_common_command,
    load_request_from_stdin,
    success_response,
)
from Resolver.containerization.runtime.launcher_normalization import ensure_graph_result


ADAPTER_NAME = os.getenv("RESOLVER_NAME", "maven-dependency-resolver")
ADAPTER_VERSION = os.getenv("ADAPTER_VERSION", "container-v1")
BACKEND_VERSION = os.getenv("BACKEND_VERSION", "legacy-java")
JAVA_MAIN_CLASS = os.getenv("MAVEN_MAIN_CLASS", "cn.edu.zju.nirvana.adapter.MavenResolverAdapterMain")
BACKEND_JAR = Path(os.getenv("MAVEN_BACKEND_JAR", "/usr/local/lib/maven-resolver.jar"))
METADATA = AdapterMetadata(
    name=ADAPTER_NAME,
    adapter_version=ADAPTER_VERSION,
    backend_version=BACKEND_VERSION,
    ecosystem="maven",
)


def normalize_backend_result(result: dict[str, Any]) -> dict[str, Any]:
    return ensure_graph_result(result, "maven")


def build_capabilities() -> dict[str, Any]:
    return {
        "commands": ["resolve", "health", "capabilities"],
        "formats": ["graph"],
        "features": ["raw", "scopes", "managed-dependencies"],
        "platform": False,
    }


def check_health() -> dict[str, Any]:
    java_binary = shutil.which("java")
    backend_ready = BACKEND_JAR.exists()
    checks = [
        {
            "name": "java_runtime",
            "status": "ok" if java_binary else "error",
            "details": java_binary or "java executable not found in PATH",
        },
        {
            "name": "backend_jar",
            "status": "ok" if backend_ready else "error",
            "details": str(BACKEND_JAR) if backend_ready else f"missing backend jar: {BACKEND_JAR}",
        },
    ]
    state = "ok" if all(check["status"] == "ok" for check in checks) else "degraded"
    return {"state": state, "checks": checks}


def build_coordinate(name: str, version: str | None) -> str:
    if version and name.count(":") == 1:
        return f"{name}:{version}"
    return name


def run_backend(coordinate: str, timeout_ms: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    java_binary = shutil.which("java")
    if not java_binary:
        return None, None, {
            "code": "BACKEND_MISCONFIGURED",
            "message": "java executable not found in PATH",
            "backend_error": None,
            "retryable": False,
        }
    if not BACKEND_JAR.exists():
        return None, None, {
            "code": "BACKEND_MISCONFIGURED",
            "message": f"maven adapter jar was not found at {BACKEND_JAR}",
            "backend_error": None,
            "retryable": False,
        }

    command = [java_binary, "-cp", str(BACKEND_JAR), JAVA_MAIN_CLASS, coordinate]
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
            "message": f"maven backend timed out after {timeout_ms}ms",
            "backend_error": None,
            "retryable": True,
        }

    raw = {
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": completed.returncode,
    }
    if completed.returncode != 0:
        backend_error = completed.stderr.strip() or None
        return None, raw, {
            "code": "BACKEND_CRASHED",
            "message": backend_error or "maven backend exited with non-zero status",
            "backend_error": "JavaProcessError",
            "retryable": False,
        }

    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return None, raw, {
            "code": "PROTOCOL_ERROR",
            "message": "maven backend did not emit valid JSON",
            "backend_error": str(exc),
            "retryable": False,
        }
    if not isinstance(result, dict):
        return None, raw, {
            "code": "PROTOCOL_ERROR",
            "message": "maven backend must return a JSON object",
            "backend_error": None,
            "retryable": False,
        }

    raw["backend_payload"] = result
    try:
        normalized_result = normalize_backend_result(result)
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
    coordinate = build_coordinate(package["name"], package.get("version"))
    timeout_ms = request.get("options", {}).get("timeout_ms", 180000)
    result, raw, error = run_backend(coordinate, timeout_ms)
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
