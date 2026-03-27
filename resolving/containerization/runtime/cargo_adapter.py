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


from resolving.containerization.runtime.adapter_runtime import (
    AdapterMetadata,
    emit_payload,
    error_response,
    handle_common_command,
    load_request_from_stdin,
    success_response,
)
from resolving.containerization.runtime.launcher_normalization import ensure_graph_result


ADAPTER_NAME = os.getenv("RESOLVER_NAME", "cargo-dependency-resolver")
ADAPTER_VERSION = os.getenv("ADAPTER_VERSION", "container-v1")
BACKEND_VERSION = os.getenv("BACKEND_VERSION", "native-rust")
BACKEND_BINARY = Path(os.getenv("CARGO_BACKEND_BINARY", "/usr/local/bin/cargo-resolver"))
CARGO_HOME = Path(os.getenv("CARGO_HOME", "/cargo-home"))
REGISTRY_MODE = os.getenv("CARGO_REGISTRY_MODE", "crates.io")
METADATA = AdapterMetadata(
    name=ADAPTER_NAME,
    adapter_version=ADAPTER_VERSION,
    backend_version=BACKEND_VERSION,
    ecosystem="cargo",
)


def normalize_backend_result(result: dict[str, Any]) -> dict[str, Any]:
    return ensure_graph_result(result, "cargo")


def _to_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value is None:
        return ""
    return str(value)


def build_capabilities() -> dict[str, Any]:
    return {
        "commands": ["resolve", "health", "capabilities"],
        "formats": ["graph", "full"],
        "features": ["raw", "features", "registry", "cache"],
        "platform": False,
    }


def check_health() -> dict[str, Any]:
    python_binary = shutil.which("python3") or shutil.which("python")
    backend_ready = BACKEND_BINARY.exists()
    cargo_home_ready = CARGO_HOME.exists()
    checks = [
        {
            "name": "python_runtime",
            "status": "ok" if python_binary else "error",
            "details": python_binary or "python runtime not found in PATH",
        },
        {
            "name": "backend_binary",
            "status": "ok" if backend_ready else "error",
            "details": str(BACKEND_BINARY) if backend_ready else f"missing backend binary: {BACKEND_BINARY}",
        },
        {
            "name": "cargo_home",
            "status": "ok" if cargo_home_ready else "error",
            "details": str(CARGO_HOME) if cargo_home_ready else f"missing cargo home: {CARGO_HOME}",
        },
        {
            "name": "registry_mode",
            "status": "ok",
            "details": REGISTRY_MODE,
        },
    ]
    state = "ok" if all(check["status"] == "ok" for check in checks) else "degraded"
    return {"state": state, "checks": checks}


def run_backend(
    crate_name: str,
    crate_version: str | None,
    format_name: str,
    timeout_ms: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    if not crate_version:
        return None, None, {
            "code": "INVALID_ARGUMENT",
            "message": "package.version is required for cargo resolve",
            "backend_error": None,
            "retryable": False,
        }

    if not BACKEND_BINARY.exists():
        return None, None, {
            "code": "BACKEND_MISCONFIGURED",
            "message": f"cargo backend binary was not found at {BACKEND_BINARY}",
            "backend_error": None,
            "retryable": False,
        }

    if format_name not in {"graph", "full"}:
        return None, None, {
            "code": "INVALID_ARGUMENT",
            "message": f"unsupported cargo format `{format_name}`",
            "backend_error": None,
            "retryable": False,
        }

    command = [str(BACKEND_BINARY), "resolve", crate_name, crate_version, "--format", format_name]
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
            "stdout": _to_text(exc.stdout),
            "stderr": _to_text(exc.stderr),
            "exit_code": None,
        }, {
            "code": "TIMEOUT",
            "message": f"cargo backend timed out after {timeout_ms}ms",
            "backend_error": None,
            "retryable": True,
        }
    except OSError as exc:
        return None, None, {
            "code": "BACKEND_MISCONFIGURED",
            "message": "failed to start cargo backend binary",
            "backend_error": str(exc),
            "retryable": False,
        }

    raw = {
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": completed.returncode,
        "backend_duration_ms": int((time.perf_counter() - backend_start) * 1000),
    }
    if completed.returncode != 0:
        backend_error = completed.stderr.strip() or None
        stderr_lower = completed.stderr.lower()
        if "no matching package named" in stderr_lower:
            error_code = "VERSION_NOT_FOUND"
        elif any(marker in stderr_lower for marker in (
            "spurious network error",
            "failed to connect",
            "securetransport error",
            "unable to update registry",
            "failed to fetch",
            "updating crates.io index",
        )):
            error_code = "DATA_SOURCE_UNAVAILABLE"
        else:
            error_code = "BACKEND_CRASHED"
        return None, raw, {
            "code": error_code,
            "message": backend_error or "cargo backend exited with non-zero status",
            "backend_error": "RustProcessError",
            "retryable": error_code != "VERSION_NOT_FOUND",
        }

    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return None, raw, {
            "code": "PROTOCOL_ERROR",
            "message": "cargo backend did not emit valid JSON",
            "backend_error": str(exc),
            "retryable": False,
        }
    if not isinstance(result, dict):
        return None, raw, {
            "code": "PROTOCOL_ERROR",
            "message": "cargo backend must return a JSON object",
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
    options = request.get("options", {})
    format_name = options.get("format", "graph")
    timeout_ms = options.get("timeout_ms", 180000)
    result, raw, error = run_backend(package["name"], package.get("version"), format_name, timeout_ms)
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
