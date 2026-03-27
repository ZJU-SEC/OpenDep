from __future__ import annotations

import importlib.util
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


ADAPTER_NAME = os.getenv("RESOLVER_NAME", "pip-dependency-resolver")
ADAPTER_VERSION = os.getenv("ADAPTER_VERSION", "container-v1")
BACKEND_VERSION = os.getenv("BACKEND_VERSION", "python-backend-v1")
BACKEND_MODULE = os.getenv(
    "PIP_BACKEND_MODULE",
    "resolving.containerization.images.pip.backend",
)
METADATA_MODE = os.getenv("PIP_METADATA_MODE", "live")
METADATA = AdapterMetadata(
    name=ADAPTER_NAME,
    adapter_version=ADAPTER_VERSION,
    backend_version=BACKEND_VERSION,
    ecosystem="pip",
)


def build_capabilities() -> dict[str, Any]:
    return {
        "commands": ["resolve", "health", "capabilities"],
        "formats": ["graph"],
        "features": ["raw", "markers", "extras", "cache", "indexed", "live"],
        "platform": False,
    }


def check_health() -> dict[str, Any]:
    python_binary = shutil.which("python3") or shutil.which("python")
    backend_module_ready = bool(BACKEND_MODULE) and importlib.util.find_spec(BACKEND_MODULE) is not None
    checks = [
        {
            "name": "python_runtime",
            "status": "ok" if python_binary else "error",
            "details": python_binary or "python runtime not found in PATH",
        },
        {
            "name": "backend_module",
            "status": "ok" if backend_module_ready else "error",
            "details": BACKEND_MODULE if backend_module_ready else f"backend module not importable: {BACKEND_MODULE}",
        },
        {
            "name": "metadata_mode",
            "status": "ok" if METADATA_MODE in {"live", "indexed"} else "error",
            "details": METADATA_MODE,
        },
        {
            "name": "index_dsn",
            "status": "ok" if METADATA_MODE != "indexed" or bool(os.getenv("PIP_INDEX_DSN")) else "degraded",
            "details": "configured" if os.getenv("PIP_INDEX_DSN") else "not configured",
        },
    ]
    state = "ok" if all(check["status"] == "ok" for check in checks) else "degraded"
    return {"state": state, "checks": checks}


def normalize_backend_result(result: dict[str, Any]) -> dict[str, Any]:
    return ensure_graph_result(result, "pip")


def _to_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value is None:
        return ""
    return str(value)


def _classify_backend_error(payload: dict[str, Any], stderr_text: str) -> tuple[str, str, bool, str | None]:
    code = str(payload.get("code") or "BACKEND_CRASHED")
    message = str(payload.get("message") or stderr_text or "pip backend exited with non-zero status")
    retryable = bool(payload.get("retryable", False))
    backend_error = str(payload.get("backend_error")) if payload.get("backend_error") is not None else None
    return code, message, retryable, backend_error


def run_backend(
    package_name: str,
    package_version: str | None,
    format_name: str,
    timeout_ms: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    python_binary = shutil.which("python3") or shutil.which("python")
    if not python_binary:
        return None, None, {
            "code": "BACKEND_MISCONFIGURED",
            "message": "python executable not found in PATH",
            "backend_error": None,
            "retryable": False,
        }

    if format_name != "graph":
        return None, None, {
            "code": "INVALID_ARGUMENT",
            "message": f"unsupported pip format `{format_name}`",
            "backend_error": None,
            "retryable": False,
        }

    command = [python_binary, "-m", BACKEND_MODULE, "resolve", "--name", package_name, "--format", format_name]
    if package_version:
        command.extend(["--version", package_version])

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
            "message": f"pip backend timed out after {timeout_ms}ms",
            "backend_error": None,
            "retryable": True,
        }
    except OSError as exc:
        return None, None, {
            "code": "BACKEND_MISCONFIGURED",
            "message": "failed to start pip backend process",
            "backend_error": str(exc),
            "retryable": False,
        }

    raw = {
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": completed.returncode,
        "backend_duration_ms": int((time.perf_counter() - backend_start) * 1000),
    }

    parsed_stdout: dict[str, Any] | None = None
    stdout_text = completed.stdout.strip()
    if stdout_text:
        try:
            decoded = json.loads(stdout_text)
            if isinstance(decoded, dict):
                parsed_stdout = decoded
                raw["backend_payload"] = decoded
        except json.JSONDecodeError:
            parsed_stdout = None

    if completed.returncode != 0:
        if parsed_stdout is not None:
            code, message, retryable, backend_error = _classify_backend_error(parsed_stdout, completed.stderr.strip())
            return None, raw, {
                "code": code,
                "message": message,
                "backend_error": backend_error,
                "retryable": retryable,
            }
        return None, raw, {
            "code": "BACKEND_CRASHED",
            "message": completed.stderr.strip() or "pip backend exited with non-zero status",
            "backend_error": "PythonProcessError",
            "retryable": False,
        }

    if parsed_stdout is None:
        return None, raw, {
            "code": "PROTOCOL_ERROR",
            "message": "pip backend did not emit valid JSON",
            "backend_error": None,
            "retryable": False,
        }

    try:
        normalized_result = normalize_backend_result(parsed_stdout)
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
    timeout_ms = options.get("timeout_ms", 1800000) # default to 30 minutes

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
