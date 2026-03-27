from __future__ import annotations

import os
import sys
import time
from pathlib import Path


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
)


def env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name, "")
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or default


METADATA = AdapterMetadata(
    name=os.getenv("RESOLVER_NAME", "container-placeholder-resolver"),
    adapter_version=os.getenv("ADAPTER_VERSION", "container-placeholder-v1"),
    backend_version=os.getenv("BACKEND_VERSION", "placeholder"),
    ecosystem=os.getenv("RESOLVER_ECOSYSTEM", "unknown"),
)


def build_capabilities() -> dict:
    return {
        "commands": env_list("RESOLVER_COMMANDS", ["resolve", "health", "capabilities"]),
        "formats": env_list("RESOLVER_FORMATS", ["graph"]),
        "features": env_list("RESOLVER_FEATURES", ["raw"]),
        "platform": False,
    }


def check_health() -> dict:
    checks = [
        {
            "name": "container_runtime",
            "status": "ok",
            "details": "placeholder container service is reachable",
        },
        {
            "name": "backend_placeholder",
            "status": "degraded",
            "details": "replace this placeholder image and command with the real backend runtime",
        },
    ]
    state = "ok" if all(check["status"] == "ok" for check in checks) else "degraded"
    return {"state": state, "checks": checks}


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

    emit_payload(
        error_response(
            request,
            METADATA,
            "BACKEND_MISCONFIGURED",
            os.getenv(
                "PLACEHOLDER_MESSAGE",
                "placeholder container is wired, but the real backend image and runtime command are not configured yet",
            ),
            None,
            False,
            start_time,
        )
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
