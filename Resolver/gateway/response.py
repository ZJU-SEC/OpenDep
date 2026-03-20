from __future__ import annotations

import json

from Resolver.gateway.contract import validate_response
from Resolver.gateway.errors import GatewayError, ProtocolError, TimeoutGatewayError
from Resolver.gateway.models import ProcessRunResult



def _should_include_raw(request: dict) -> bool:
    options = request.get("options")
    if not isinstance(options, dict):
        return False
    return bool(options.get("return_raw"))



def _raw_payload_for_response(request: dict, raw: dict | None) -> dict | None:
    if not _should_include_raw(request):
        return None
    return raw


class GatewayResponseFactory:
    def error_response(
        self,
        request: dict,
        error: GatewayError,
        resolver_name: str,
        adapter_version: str = "v1",
        backend_version: str | None = None,
        raw: dict | None = None,
    ) -> dict:
        return {
            "schema_version": "1.0",
            "request_id": request.get("request_id", "unknown"),
            "trace_id": request.get("trace_id", "unknown"),
            "status": "error",
            "ecosystem": request.get("ecosystem", "unknown"),
            "resolver": {
                "name": resolver_name,
                "adapter_version": adapter_version,
                "backend_version": backend_version,
            },
            "error": {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
                "backend_error": error.backend_error,
            },
            "diagnostics": [],
            "raw": _raw_payload_for_response(request, raw),
            "timing": None,
        }


class AdapterResponseNormalizer:
    def __init__(self, response_factory: GatewayResponseFactory | None = None) -> None:
        self.response_factory = response_factory or GatewayResponseFactory()

    def normalize(self, request: dict, resolver: dict, run_result: ProcessRunResult) -> dict:
        if run_result.timeout:
            error = TimeoutGatewayError(
                f"resolver timed out after {request.get('options', {}).get('timeout_ms') or resolver.get('timeout_ms', 60000)}ms"
            )
            return self.response_factory.error_response(
                request,
                error,
                resolver_name=f"{request['ecosystem']}-resolver",
                adapter_version="gateway-v1",
                backend_version=None,
                raw=run_result.raw_payload(),
            )

        stdout = run_result.stdout.strip()

        try:
            payload = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            error = ProtocolError("adapter did not return valid JSON")
            return self.response_factory.error_response(
                request,
                error,
                resolver_name=f"{request['ecosystem']}-resolver",
                adapter_version="gateway-v1",
                backend_version=None,
                raw=run_result.raw_payload(),
            )

        errors = validate_response(payload)
        if errors:
            error = ProtocolError("; ".join(errors))
            return self.response_factory.error_response(
                request,
                error,
                resolver_name=f"{request['ecosystem']}-resolver",
                adapter_version="gateway-v1",
                backend_version=None,
                raw=run_result.raw_payload(),
            )

        if _should_include_raw(request):
            payload["raw"] = payload.get("raw") if payload.get("raw") is not None else run_result.raw_payload()
        else:
            payload["raw"] = None
        return payload


def wrap_timeout_response(request: dict, resolver: dict, run_result: dict) -> dict:
    result = ProcessRunResult(
        timeout=run_result.get("timeout", False),
        stdout=run_result.get("stdout", ""),
        stderr=run_result.get("stderr", ""),
        exit_code=run_result.get("exit_code"),
    )
    return AdapterResponseNormalizer().normalize(request, resolver, result)



def normalize_adapter_response(request: dict, resolver: dict, run_result: dict) -> dict:
    result = ProcessRunResult(
        timeout=run_result.get("timeout", False),
        stdout=run_result.get("stdout", ""),
        stderr=run_result.get("stderr", ""),
        exit_code=run_result.get("exit_code"),
    )
    return AdapterResponseNormalizer().normalize(request, resolver, result)
