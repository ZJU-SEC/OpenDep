from __future__ import annotations

from typing import Any


SUPPORTED_COMMANDS = {"resolve", "list", "health", "capabilities"}


def validate_request(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["request must be a JSON object"]

    for key in ["schema_version", "request_id", "trace_id", "command", "ecosystem"]:
        if key not in payload:
            errors.append(f"missing required field: {key}")

    if errors:
        return errors

    if payload.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")

    command = payload.get("command")
    if command not in SUPPORTED_COMMANDS:
        errors.append(f"unsupported command: {command}")

    ecosystem = payload.get("ecosystem")
    if not isinstance(ecosystem, str) or not ecosystem:
        errors.append("ecosystem must be a non-empty string")

    if command in {"resolve", "list"}:
        package = payload.get("package")
        if not isinstance(package, dict):
            errors.append(f"package must be present for {command}")
        else:
            name = package.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"package.name is required for {command}")

    return errors


def validate_response(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["response must be a JSON object"]

    for key in ["schema_version", "request_id", "trace_id", "status", "ecosystem", "resolver"]:
        if key not in payload:
            errors.append(f"missing required field: {key}")

    if errors:
        return errors

    if payload.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")

    status = payload.get("status")
    if status not in {"ok", "error"}:
        errors.append("status must be 'ok' or 'error'")

    resolver = payload.get("resolver")
    if not isinstance(resolver, dict):
        errors.append("resolver must be an object")
    else:
        if not resolver.get("name"):
            errors.append("resolver.name is required")
        if not resolver.get("adapter_version"):
            errors.append("resolver.adapter_version is required")

    if status == "ok" and "result" not in payload:
        errors.append("result is required when status is 'ok'")

    if status == "error":
        error = payload.get("error")
        if not isinstance(error, dict):
            errors.append("error object is required when status is 'error'")
        else:
            if not error.get("code"):
                errors.append("error.code is required")
            if not error.get("message"):
                errors.append("error.message is required")
            if "retryable" not in error:
                errors.append("error.retryable is required")

    return errors
