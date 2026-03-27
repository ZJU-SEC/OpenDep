from __future__ import annotations

import json
from pathlib import Path

from pip_models import BuildRequest


def _normalize_versions(item: dict[str, object]) -> tuple[str, ...]:
    if isinstance(item.get("versions"), list):
        values = [str(value).strip() for value in item["versions"] if str(value).strip()]
        return tuple(values)
    if item.get("version"):
        normalized = str(item["version"]).strip()
        return (normalized,) if normalized else ()
    return ()


def _normalize_item(item: object, *, base_dir: Path, defaults: dict[str, object] | None = None) -> BuildRequest:
    if not isinstance(item, dict):
        raise ValueError("manifest items must be objects")

    merged = dict(defaults or {})
    merged.update(item)

    project_name = str(merged["project_name"]) if merged.get("project_name") else (
        str(merged["name"]) if merged.get("name") else None
    )
    versions = _normalize_versions(merged)
    limit = int(merged["limit"]) if merged.get("limit") is not None else None
    include_yanked = bool(merged.get("include_yanked", False))
    mirror_dir = None
    if merged.get("mirror_dir"):
        mirror_path = Path(str(merged["mirror_dir"]))
        mirror_dir = str((base_dir / mirror_path).resolve()) if not mirror_path.is_absolute() else str(mirror_path.resolve())

    raw_path = merged.get("artifact_path") or merged.get("artifact")
    if raw_path:
        artifact_path = Path(str(raw_path))
        if not artifact_path.is_absolute():
            artifact_path = (base_dir / artifact_path).resolve()
        if len(versions) > 1:
            raise ValueError("artifact manifest items support at most one explicit version")
        return BuildRequest(
            artifact_path=str(artifact_path),
            project_name=project_name,
            versions=versions,
            mirror_dir=mirror_dir,
        )

    if not project_name:
        raise ValueError("manifest item must contain either `artifact_path` or `project_name` / `name`")

    return BuildRequest(
        project_name=project_name,
        versions=versions,
        limit=limit,
        include_yanked=include_yanked,
        mirror_dir=mirror_dir,
    )


class ManifestAdapter:
    def load(self, manifest_path: str) -> list[BuildRequest]:
        path = Path(manifest_path).expanduser().resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
        defaults: dict[str, object] | None = None

        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            defaults = dict(payload.get("defaults", {})) if isinstance(payload.get("defaults"), dict) else None
            if isinstance(payload.get("jobs"), list):
                items = payload["jobs"]
            elif isinstance(payload.get("artifacts"), list):
                items = payload["artifacts"]
            elif isinstance(payload.get("packages"), list):
                items = payload["packages"]
            else:
                raise ValueError("manifest must contain a top-level `jobs`, `artifacts`, or `packages` list")
        else:
            raise ValueError("manifest must be a JSON object or list")

        return [_normalize_item(item, base_dir=path.parent, defaults=defaults) for item in items]
