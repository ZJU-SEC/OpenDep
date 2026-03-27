from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def container_config_path() -> Path:
    return PROJECT_ROOT / "resolving" / "config" / "resolvers.container.yaml"


def host_config_path() -> Path:
    return PROJECT_ROOT / "resolving" / "config" / "resolvers.yaml"


def default_config_path(ecosystem: str | None = None) -> Path:
    if ecosystem:
        normalized = ecosystem.strip().lower()
        container_path = container_config_path()
        if _config_supports_ecosystem(container_path, normalized):
            return container_path

        legacy_path = host_config_path()
        if _config_supports_ecosystem(legacy_path, normalized):
            return legacy_path

    return container_config_path()


def load_config(path: str | Path | None = None, ecosystem: str | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else default_config_path(ecosystem)
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return normalize_config(data)


def normalize_config(data: dict[str, Any]) -> dict[str, Any]:
    normalized = {"resolvers": []}
    for resolver in data.get("resolvers", []):
        item = dict(resolver)
        item["command"] = [_resolve_placeholder(arg) for arg in item.get("command", [])]
        item["command"] = [_resolve_command_path(arg) for arg in item["command"]]
        item["workdir"] = str(_resolve_workdir(item.get("workdir", ".")))
        normalized["resolvers"].append(item)
    return normalized


def _config_supports_ecosystem(path: Path, ecosystem: str) -> bool:
    if not path.exists():
        return False

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    for resolver in data.get("resolvers", []):
        candidate = str(resolver.get("ecosystem", "")).strip().lower()
        if candidate == ecosystem:
            return True
    return False


def _resolve_placeholder(value: Any) -> Any:
    if value == "${PYTHON}":
        return sys.executable
    return value


def _resolve_command_path(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    candidate = PROJECT_ROOT / value
    if candidate.exists():
        return str(candidate)
    return value


def _resolve_workdir(value: str) -> Path:
    candidate = PROJECT_ROOT / value
    if candidate.exists():
        return candidate
    return PROJECT_ROOT


def build_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(os.environ)
    if extra_env:
        merged.update(extra_env)
    return merged
