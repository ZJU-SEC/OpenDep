from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

from Resolver.gateway.contract import validate_request


@dataclass(frozen=True)
class AdapterMetadata:
    name: str
    adapter_version: str
    backend_version: str | None
    ecosystem: str


CapabilitiesBuilder = Callable[[], dict[str, Any]]
HealthChecker = Callable[[], dict[str, Any]]


def _request_envelope(request: Any, metadata: AdapterMetadata) -> tuple[str, str, str]:
    if isinstance(request, dict):
        return (
            request.get("request_id", "unknown"),
            request.get("trace_id", "unknown"),
            request.get("ecosystem", metadata.ecosystem),
        )
    return "unknown", "unknown", metadata.ecosystem



def _duration_ms(start_time: float) -> int:
    return int((time.perf_counter() - start_time) * 1000)



def _should_include_raw(request: Any) -> bool:
    if not isinstance(request, dict):
        return False
    options = request.get("options")
    if not isinstance(options, dict):
        return False
    return bool(options.get("return_raw"))



def _raw_payload_for_response(request: Any, raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not _should_include_raw(request):
        return None
    return raw



def success_response(
    request: dict[str, Any],
    metadata: AdapterMetadata,
    result: dict[str, Any],
    start_time: float,
    raw: dict[str, Any] | None = None,
    use_result_timing: bool = False,
) -> dict[str, Any]:
    request_id, trace_id, ecosystem = _request_envelope(request, metadata)
    timing: dict[str, Any] | None = {"duration_ms": _duration_ms(start_time)}
    if use_result_timing and isinstance(result, dict):
        timing = result.get("timing", timing)

    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "request_id": request_id,
        "trace_id": trace_id,
        "status": "ok",
        "ecosystem": ecosystem,
        "resolver": {
            "name": metadata.name,
            "adapter_version": metadata.adapter_version,
            "backend_version": metadata.backend_version,
        },
        "result": result,
        "diagnostics": [],
        "raw": _raw_payload_for_response(request, raw),
        "timing": timing,
    }
    metrics = result.get("metrics") if isinstance(result, dict) else None
    if metrics is not None:
        payload["metrics"] = metrics
    return payload



def error_response(
    request: Any,
    metadata: AdapterMetadata,
    code: str,
    message: str,
    backend_error: str | None,
    retryable: bool,
    start_time: float,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_id, trace_id, ecosystem = _request_envelope(request, metadata)
    return {
        "schema_version": "1.0",
        "request_id": request_id,
        "trace_id": trace_id,
        "status": "error",
        "ecosystem": ecosystem,
        "resolver": {
            "name": metadata.name,
            "adapter_version": metadata.adapter_version,
            "backend_version": metadata.backend_version,
        },
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "backend_error": backend_error,
        },
        "diagnostics": [],
        "raw": _raw_payload_for_response(request, raw),
        "timing": {"duration_ms": _duration_ms(start_time)},
    }



def emit_payload(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))



def load_request_from_stdin(metadata: AdapterMetadata, start_time: float) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    raw_request = sys.stdin.read().strip()
    if not raw_request:
        return None, error_response(
            {},
            metadata,
            "INVALID_ARGUMENT",
            "stdin request body is required",
            None,
            False,
            start_time,
        )

    try:
        request = json.loads(raw_request)
    except json.JSONDecodeError as exc:
        return None, error_response(
            {},
            metadata,
            "INVALID_ARGUMENT",
            "request must be valid JSON",
            str(exc),
            False,
            start_time,
        )

    request_errors = validate_request(request)
    if request_errors:
        return None, error_response(
            request,
            metadata,
            "INVALID_ARGUMENT",
            "; ".join(request_errors),
            None,
            False,
            start_time,
        )

    return request, None



def handle_common_command(
    request: dict[str, Any],
    metadata: AdapterMetadata,
    start_time: float,
    capabilities_builder: CapabilitiesBuilder,
    health_checker: HealthChecker,
) -> tuple[int, dict[str, Any]] | None:
    command = request["command"]
    if command == "capabilities":
        return 0, success_response(
            request,
            metadata,
            {"capabilities": capabilities_builder()},
            start_time,
        )

    if command == "health":
        return 0, success_response(
            request,
            metadata,
            {"health": health_checker()},
            start_time,
        )

    if command != "resolve":
        return 1, error_response(
            request,
            metadata,
            "UNSUPPORTED_COMMAND",
            f"unsupported command: {command}",
            None,
            False,
            start_time,
        )

    return None
