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


ADAPTER_NAME = os.getenv("RESOLVER_NAME", "go-dependency-resolver")
ADAPTER_VERSION = os.getenv("ADAPTER_VERSION", "container-v1")
BACKEND_VERSION = os.getenv("BACKEND_VERSION", "native-go")
BACKEND_BINARY = Path(os.getenv("GO_BACKEND_BINARY", "/usr/local/bin/go-resolver"))
METADATA_MODE = (os.getenv("GO_METADATA_MODE", "online").strip() or "online").lower()
PROXY_BASE_URL = os.getenv("GO_PROXY_BASE_URL", "https://proxy.golang.org")
INDEX_DSN = os.getenv("GO_INDEX_DSN", "").strip()
INDEX_TABLE = os.getenv("GO_INDEX_TABLE", "go_metadata").strip() or "go_metadata"
INDEX_FALLBACK_TO_ONLINE = (
    os.getenv("GO_INDEX_FALLBACK_TO_ONLINE", "true").strip().lower() in {"1", "true", "yes", "on"}
)
DEFAULT_TIMEOUT_MS = int(os.getenv("GO_DEFAULT_TIMEOUT_MS", "120000"))
METADATA = AdapterMetadata(
    name=ADAPTER_NAME,
    adapter_version=ADAPTER_VERSION,
    backend_version=BACKEND_VERSION,
    ecosystem="go",
)

KNOWN_BACKEND_ERRORS = {
    "INVALID_ARGUMENT": ("INVALID_ARGUMENT", False),
    "VERSION_NOT_FOUND": ("VERSION_NOT_FOUND", False),
    "PACKAGE_NOT_FOUND": ("PACKAGE_NOT_FOUND", False),
    "DATA_SOURCE_UNAVAILABLE": ("DATA_SOURCE_UNAVAILABLE", True),
    "BACKEND_MISCONFIGURED": ("BACKEND_MISCONFIGURED", False),
    "UNSUPPORTED_REPLACE": ("UNSUPPORTED_REPLACE", False),
    "PROTOCOL_ERROR": ("PROTOCOL_ERROR", False),
}


def normalize_backend_result(result: dict[str, Any]) -> dict[str, Any]:
    return ensure_graph_result(result, "go")


def _to_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value is None:
        return ""
    return str(value)


def build_capabilities() -> dict[str, Any]:
    return {
        "commands": ["resolve", "list", "health", "capabilities"],
        "formats": ["graph", "full"],
        "features": ["raw", "replace", "exclude", "buildlist", "indexed-postgres"],
        "metadata_modes": ["online", "indexed"],
        "platform": False,
    }


def check_health() -> dict[str, Any]:
    python_binary = shutil.which("python3") or shutil.which("python")
    backend_ready = BACKEND_BINARY.exists()
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
            "name": "go_metadata_mode",
            "status": "ok" if METADATA_MODE in {"online", "indexed"} else "error",
            "details": METADATA_MODE,
        },
    ]
    if METADATA_MODE == "online" or INDEX_FALLBACK_TO_ONLINE:
        checks.append(
            {
                "name": "go_proxy_base_url",
                "status": "ok" if PROXY_BASE_URL else "error",
                "details": PROXY_BASE_URL or "GO_PROXY_BASE_URL is empty",
            }
        )
    if METADATA_MODE == "indexed":
        checks.extend(
            [
                {
                    "name": "go_index_dsn",
                    "status": "ok" if INDEX_DSN else "error",
                    "details": "configured" if INDEX_DSN else "GO_INDEX_DSN is not set",
                },
                {
                    "name": "go_index_table",
                    "status": "ok" if INDEX_TABLE else "error",
                    "details": INDEX_TABLE or "GO_INDEX_TABLE is empty",
                },
            ]
        )
    state = "ok" if all(check["status"] == "ok" for check in checks) else "degraded"
    return {"state": state, "checks": checks}


def classify_backend_failure(stderr: str) -> tuple[str, bool]:
    stripped = stderr.strip()
    if stripped:
        prefix = stripped.split(":", 1)[0].strip()
        if prefix in KNOWN_BACKEND_ERRORS:
            return KNOWN_BACKEND_ERRORS[prefix]

    stderr_lower = stripped.lower()
    if "module version not found" in stderr_lower:
        return "VERSION_NOT_FOUND", False
    if any(marker in stderr_lower for marker in (
        "proxy returned status",
        "proxy request failed",
        "postgres index query failed",
        "failed to read go proxy response",
        "context deadline exceeded",
        "i/o timeout",
        "connection refused",
        "no such host",
    )):
        return "DATA_SOURCE_UNAVAILABLE", True
    if "go_index_dsn is required" in stderr_lower or "failed to initialize indexed metadata source" in stderr_lower:
        return "BACKEND_MISCONFIGURED", False
    return "BACKEND_CRASHED", False


def run_resolve_backend(
    module_name: str,
    module_version: str | None,
    format_name: str,
    timeout_ms: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    if not module_version:
        return None, None, {
            "code": "INVALID_ARGUMENT",
            "message": "package.version is required for go resolve",
            "backend_error": None,
            "retryable": False,
        }

    if not BACKEND_BINARY.exists():
        return None, None, {
            "code": "BACKEND_MISCONFIGURED",
            "message": f"go backend binary was not found at {BACKEND_BINARY}",
            "backend_error": None,
            "retryable": False,
        }

    if format_name not in {"graph", "full"}:
        return None, None, {
            "code": "INVALID_ARGUMENT",
            "message": f"unsupported go format `{format_name}`",
            "backend_error": None,
            "retryable": False,
        }

    command = [str(BACKEND_BINARY), "resolve", module_name, module_version, "--format", format_name]
    env = os.environ.copy()
    env["GO_METADATA_MODE"] = METADATA_MODE
    if PROXY_BASE_URL:
        env["GO_PROXY_BASE_URL"] = PROXY_BASE_URL
    if INDEX_DSN:
        env["GO_INDEX_DSN"] = INDEX_DSN
    if INDEX_TABLE:
        env["GO_INDEX_TABLE"] = INDEX_TABLE
    env["GO_INDEX_FALLBACK_TO_ONLINE"] = "true" if INDEX_FALLBACK_TO_ONLINE else "false"

    backend_start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            env=env,
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
            "message": f"go backend timed out after {timeout_ms}ms",
            "backend_error": None,
            "retryable": True,
        }
    except OSError as exc:
        return None, None, {
            "code": "BACKEND_MISCONFIGURED",
            "message": "failed to start go backend binary",
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
        error_code, retryable = classify_backend_failure(completed.stderr)
        return None, raw, {
            "code": error_code,
            "message": completed.stderr.strip() or "go backend exited with non-zero status",
            "backend_error": "GoProcessError",
            "retryable": retryable,
        }

    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return None, raw, {
            "code": "PROTOCOL_ERROR",
            "message": "go backend did not emit valid JSON",
            "backend_error": str(exc),
            "retryable": False,
        }
    if not isinstance(result, dict):
        return None, raw, {
            "code": "PROTOCOL_ERROR",
            "message": "go backend must return a JSON object",
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


def run_list_backend(
    module_name: str,
    module_version: str | None,
    timeout_ms: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    if not module_version:
        return None, None, {
            "code": "INVALID_ARGUMENT",
            "message": "package.version is required for go list",
            "backend_error": None,
            "retryable": False,
        }

    if not BACKEND_BINARY.exists():
        return None, None, {
            "code": "BACKEND_MISCONFIGURED",
            "message": f"go backend binary was not found at {BACKEND_BINARY}",
            "backend_error": None,
            "retryable": False,
        }

    command = [str(BACKEND_BINARY), "list", module_name, module_version, "--json"]
    env = os.environ.copy()
    env["GO_METADATA_MODE"] = METADATA_MODE
    if PROXY_BASE_URL:
        env["GO_PROXY_BASE_URL"] = PROXY_BASE_URL
    if INDEX_DSN:
        env["GO_INDEX_DSN"] = INDEX_DSN
    if INDEX_TABLE:
        env["GO_INDEX_TABLE"] = INDEX_TABLE
    env["GO_INDEX_FALLBACK_TO_ONLINE"] = "true" if INDEX_FALLBACK_TO_ONLINE else "false"

    backend_start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            env=env,
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
            "message": f"go backend timed out after {timeout_ms}ms",
            "backend_error": None,
            "retryable": True,
        }
    except OSError as exc:
        return None, None, {
            "code": "BACKEND_MISCONFIGURED",
            "message": "failed to start go backend binary",
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
        error_code, retryable = classify_backend_failure(completed.stderr)
        return None, raw, {
            "code": error_code,
            "message": completed.stderr.strip() or "go backend exited with non-zero status",
            "backend_error": "GoProcessError",
            "retryable": retryable,
        }

    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return None, raw, {
            "code": "PROTOCOL_ERROR",
            "message": "go backend did not emit valid JSON for list",
            "backend_error": str(exc),
            "retryable": False,
        }
    if not isinstance(result, dict):
        return None, raw, {
            "code": "PROTOCOL_ERROR",
            "message": "go backend list must return a JSON object",
            "backend_error": None,
            "retryable": False,
        }

    raw["backend_payload"] = result
    return {"list": result, "metrics": dict(result.get("metrics", {}))}, raw, None


def main() -> int:
    start_time = time.perf_counter()
    request, request_error = load_request_from_stdin(METADATA, start_time)
    if request_error is not None:
        emit_payload(request_error)
        return 1

    if request["command"] in {"capabilities", "health"}:
        common_response = handle_common_command(request, METADATA, start_time, build_capabilities, check_health)
        if common_response is not None:
            exit_code, payload = common_response
            emit_payload(payload)
            return exit_code
    elif request["command"] not in {"resolve", "list"}:
        emit_payload(
            error_response(
                request,
                METADATA,
                "UNSUPPORTED_COMMAND",
                f"unsupported command: {request['command']}",
                None,
                False,
                start_time,
            )
        )
        return 1

    package = request["package"]
    options = request.get("options", {})
    format_name = options.get("format", "graph")
    timeout_ms = options.get("timeout_ms", DEFAULT_TIMEOUT_MS)
    if request["command"] == "list":
        result, raw, error = run_list_backend(package["name"], package.get("version"), timeout_ms)
    else:
        result, raw, error = run_resolve_backend(package["name"], package.get("version"), format_name, timeout_ms)
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
