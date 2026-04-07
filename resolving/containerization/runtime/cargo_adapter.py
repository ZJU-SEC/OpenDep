from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import hashlib
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


SUPPORTED_METADATA_MODES = {"indexed", "online"}


def _normalize_metadata_mode(raw_mode: str | None) -> str:
    mode = (raw_mode or "").strip().lower()
    if mode == "local-registry":
        return "indexed"
    if mode == "crates.io":
        return "online"
    return mode


def _metadata_mode_from_env() -> str:
    explicit_mode = os.getenv("CARGO_METADATA_MODE")
    if explicit_mode and explicit_mode.strip():
        return _normalize_metadata_mode(explicit_mode)
    legacy_mode = os.getenv("CARGO_REGISTRY_MODE")
    if legacy_mode and legacy_mode.strip():
        return _normalize_metadata_mode(legacy_mode)
    return "indexed"


def _shared_data_root_from_env() -> Path:
    shared_root = os.getenv("CARGO_SHARED_DATA_ROOT")
    if shared_root and shared_root.strip():
        return Path(shared_root)

    legacy_root = os.getenv("CARGO_PREPROCESS_DATA_ROOT")
    if legacy_root and legacy_root.strip():
        return Path(legacy_root)

    return Path("/cargo-data")


ADAPTER_NAME = os.getenv("RESOLVER_NAME", "cargo-dependency-resolver")
ADAPTER_VERSION = os.getenv("ADAPTER_VERSION", "container-v1")
BACKEND_VERSION = os.getenv("BACKEND_VERSION", "native-rust")
BACKEND_BINARY = Path(os.getenv("CARGO_BACKEND_BINARY", "/usr/local/bin/cargo-resolver-runtime"))
SHARED_DATA_ROOT = _shared_data_root_from_env()
CARGO_HOME = Path(os.getenv("CARGO_HOME", str(SHARED_DATA_ROOT / "cargo-home")))
RUNTIME_ROOT = Path(os.getenv("CARGO_RUNTIME_ROOT", "/opt/opendep/cargo-runtime"))
LOCAL_REGISTRY_DIR = Path(os.getenv("CARGO_LOCAL_REGISTRY_DIR", str(SHARED_DATA_ROOT / "local-registry")))
METADATA_MODE = _metadata_mode_from_env()
LEGACY_REGISTRY_MODE = (os.getenv("CARGO_REGISTRY_MODE", "").strip() or None)
RUNTIME_CONFIG_DIR = RUNTIME_ROOT / ".cargo"
RUNTIME_CONFIG_PATH = RUNTIME_CONFIG_DIR / "config.toml"
RUNTIME_CONFIG_TEMPLATE_PATHS = {
    "indexed": RUNTIME_CONFIG_DIR / "config.indexed.toml",
    "online": RUNTIME_CONFIG_DIR / "config.online.toml",
}
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


def _looks_like_local_registry(path: Path) -> bool:
    return (path / "index" / "config.json").exists()


def _registry_config_path(metadata_mode: str, path: Path) -> Path:
    if metadata_mode == "indexed":
        return path / "index" / "config.json"
    return RUNTIME_CONFIG_PATH


def _registry_layout_name(metadata_mode: str) -> str:
    if metadata_mode == "indexed":
        return "local-registry"
    return "network crates.io"


def _runtime_config_template_path(metadata_mode: str) -> Path:
    return RUNTIME_CONFIG_TEMPLATE_PATHS[metadata_mode]


def _active_registry_dir(metadata_mode: str) -> Path:
    if metadata_mode == "indexed":
        return LOCAL_REGISTRY_DIR
    return CARGO_HOME


def _looks_like_registry(metadata_mode: str, path: Path) -> bool:
    if metadata_mode == "indexed":
        return _looks_like_local_registry(path)
    if metadata_mode == "online":
        return path.exists()
    return False


def _registry_source(metadata_mode: str) -> str:
    if metadata_mode == "indexed":
        return "preprocess-local-registry"
    return "network-crates-io"


def _runtime_config_details(metadata_mode: str) -> dict[str, str]:
    return {
        "template_path": str(_runtime_config_template_path(metadata_mode)),
        "active_path": str(RUNTIME_CONFIG_PATH),
    }


def _ensure_runtime_config_ready(metadata_mode: str) -> dict[str, str]:
    if metadata_mode not in SUPPORTED_METADATA_MODES:
        raise RuntimeError(
            f"unsupported cargo metadata mode `{metadata_mode}`; expected `indexed` or `online`"
        )

    template_path = _runtime_config_template_path(metadata_mode)
    if not template_path.exists():
        raise RuntimeError(
            "missing Cargo runtime config template at "
            f"{template_path}; rebuild the resolver-cargo image"
        )

    RUNTIME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not RUNTIME_CONFIG_PATH.exists() or RUNTIME_CONFIG_PATH.read_bytes() != template_path.read_bytes():
        shutil.copyfile(template_path, RUNTIME_CONFIG_PATH)

    return _runtime_config_details(metadata_mode)


def _registry_config_sha256(metadata_mode: str, path: Path) -> str | None:
    if metadata_mode == "online":
        return None
    config_path = _registry_config_path(metadata_mode, path)
    if not config_path.exists():
        return None
    return hashlib.sha256(config_path.read_bytes()).hexdigest()


def _registry_candidate_details(metadata_mode: str, path: Path) -> str:
    if metadata_mode == "online":
        return f"cache-root: {path.resolve()}"
    if _looks_like_registry(metadata_mode, path):
        return f"available: {path.resolve()}"
    return f"missing: {_registry_config_path(metadata_mode, path)}"


def _missing_registry_error(metadata_mode: str, path: Path) -> str:
    expected_config = _registry_config_path(metadata_mode, path)
    if metadata_mode == "indexed":
        return (
            "no preprocess-managed Cargo local-registry was found at "
            f"{expected_config}; prepare pre-process/cargo data with "
            "`prepare-local-registry` and mount the shared volume into the resolver container"
        )
    return f"Cargo online cache root is not available at {path}"


def ensure_runtime_registry_ready() -> dict[str, Any]:
    runtime_config = _ensure_runtime_config_ready(METADATA_MODE)
    CARGO_HOME.mkdir(parents=True, exist_ok=True)
    selected_dir = _active_registry_dir(METADATA_MODE)
    if METADATA_MODE == "online":
        selected_dir.mkdir(parents=True, exist_ok=True)
    elif not _looks_like_registry(METADATA_MODE, selected_dir):
        raise RuntimeError(_missing_registry_error(METADATA_MODE, selected_dir))

    selected_path = selected_dir.resolve()
    return {
        "metadata_mode": METADATA_MODE,
        "source": _registry_source(METADATA_MODE),
        "active_path": str(selected_path),
        "config_sha256": _registry_config_sha256(METADATA_MODE, selected_path),
        "config_path": (
            str(_registry_config_path(METADATA_MODE, selected_path))
            if METADATA_MODE == "indexed"
            else None
        ),
        "runtime_config": runtime_config,
    }


def build_capabilities() -> dict[str, Any]:
    return {
        "commands": ["resolve", "health", "capabilities"],
        "formats": ["graph", "full"],
        "features": [
            "raw",
            "features",
            "registry",
            "cache",
            "indexed-local-registry",
            "online-network",
        ],
        "metadata_modes": ["indexed", "online"],
        "platform": False,
    }


def check_health() -> dict[str, Any]:
    registry_binding_error = None
    registry_binding: dict[str, Any] | None = None
    try:
        registry_binding = ensure_runtime_registry_ready()
    except RuntimeError as exc:
        registry_binding_error = str(exc)

    python_binary = shutil.which("python3") or shutil.which("python")
    backend_ready = BACKEND_BINARY.exists()
    cargo_home_ready = CARGO_HOME.exists()
    runtime_root_ready = RUNTIME_ROOT.exists()
    runtime_config_template_path = (
        _runtime_config_template_path(METADATA_MODE)
        if METADATA_MODE in SUPPORTED_METADATA_MODES
        else None
    )
    runtime_config_template_ready = (
        runtime_config_template_path is not None and runtime_config_template_path.exists()
    )
    runtime_config_ready = RUNTIME_CONFIG_PATH.exists()
    active_registry_dir = _active_registry_dir(METADATA_MODE) if METADATA_MODE in SUPPORTED_METADATA_MODES else None
    runtime_registry_ready = False
    if active_registry_dir is not None:
        if METADATA_MODE == "online":
            runtime_registry_ready = active_registry_dir.exists()
        else:
            runtime_registry_ready = _looks_like_registry(METADATA_MODE, active_registry_dir)
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
            "name": "runtime_root",
            "status": "ok" if runtime_root_ready else "error",
            "details": str(RUNTIME_ROOT) if runtime_root_ready else f"missing runtime root: {RUNTIME_ROOT}",
        },
        {
            "name": "cargo_metadata_mode",
            "status": "ok" if METADATA_MODE in SUPPORTED_METADATA_MODES else "error",
            "details": METADATA_MODE,
        },
        {
            "name": "runtime_config_template",
            "status": "ok" if runtime_config_template_ready else "error",
            "details": (
                str(runtime_config_template_path)
                if runtime_config_template_ready
                else f"missing runtime Cargo config template: {runtime_config_template_path}"
            ),
        },
        {
            "name": "runtime_config",
            "status": "ok" if runtime_config_ready else "error",
            "details": str(RUNTIME_CONFIG_PATH) if runtime_config_ready else "missing active runtime Cargo config",
        },
        {
            "name": "shared_data_root",
            "status": "ok" if SHARED_DATA_ROOT.exists() else "error",
            "details": str(SHARED_DATA_ROOT),
        },
        {
            "name": "runtime_registry",
            "status": "ok" if runtime_registry_ready else "error",
            "details": (
                (
                    str(_registry_config_path(METADATA_MODE, active_registry_dir))
                    if METADATA_MODE == "indexed"
                    else str(active_registry_dir)
                )
                if runtime_registry_ready and active_registry_dir is not None
                else f"missing {_registry_layout_name(METADATA_MODE)} runtime data"
            ),
        },
        {
            "name": "preprocess_registry_mount",
            "status": (
                "ok"
                if (METADATA_MODE == "online" or runtime_registry_ready)
                else "error"
            ),
            "details": (
                _registry_candidate_details(METADATA_MODE, active_registry_dir)
                if active_registry_dir is not None
                else "unsupported cargo metadata mode"
            ),
        },
        {
            "name": "runtime_registry_source",
            "status": "ok" if registry_binding is not None else "error",
            "details": registry_binding["source"] if registry_binding is not None else registry_binding_error,
        },
        {
            "name": "runtime_registry_active_path",
            "status": "ok" if registry_binding is not None else "error",
            "details": registry_binding["active_path"] if registry_binding is not None else registry_binding_error,
        },
        {
            "name": "runtime_registry_config_sha256",
            "status": "ok" if registry_binding is not None else "error",
            "details": (
                registry_binding["config_sha256"]
                if registry_binding is not None and registry_binding["config_sha256"] is not None
                else (
                    "not required in online mode"
                    if registry_binding is not None
                    else registry_binding_error
                )
            ),
        },
        {
            "name": "runtime_registry_config_path",
            "status": "ok",
            "details": (
                (
                    registry_binding["config_path"]
                    if registry_binding["config_path"] is not None
                    else "not required in online mode"
                )
                if registry_binding is not None
                else (
                    (
                        str(_registry_config_path(METADATA_MODE, active_registry_dir))
                        if METADATA_MODE == "indexed" and active_registry_dir is not None
                        else "not required in online mode"
                    )
                )
            ),
        },
        {
            "name": "legacy_registry_mode",
            "status": "ok",
            "details": LEGACY_REGISTRY_MODE or "unset",
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

    try:
        registry_binding = ensure_runtime_registry_ready()
    except RuntimeError as exc:
        return None, None, {
            "code": "BACKEND_MISCONFIGURED",
            "message": str(exc),
            "backend_error": exc.__class__.__name__,
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
    env = os.environ.copy()
    env["CARGO_METADATA_MODE"] = METADATA_MODE
    env["CARGO_SHARED_DATA_ROOT"] = str(SHARED_DATA_ROOT)
    env["CARGO_LOCAL_REGISTRY_DIR"] = str(LOCAL_REGISTRY_DIR)
    env["CARGO_RUNTIME_ROOT"] = str(RUNTIME_ROOT)
    env["CARGO_HOME"] = str(CARGO_HOME)
    backend_start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=RUNTIME_ROOT,
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
        "metadata_mode": registry_binding["metadata_mode"],
        "runtime_registry_source": registry_binding["source"],
        "runtime_registry_active_path": registry_binding["active_path"],
        "runtime_registry_config_sha256": registry_binding["config_sha256"],
        "runtime_registry_config_path": registry_binding["config_path"],
        "runtime_config_path": registry_binding["runtime_config"]["active_path"],
        "runtime_config_template_path": registry_binding["runtime_config"]["template_path"],
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
            "failed to fetch cargo crate metadata",
            "failed to fetch cargo dependency metadata",
            "crates.io api returned status",
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
