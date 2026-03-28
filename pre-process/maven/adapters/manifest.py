from __future__ import annotations

import json
from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
MAVEN_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]

for path in (MAVEN_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from maven_models import MavenCoordinate, WarmRequest


def _normalize_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def _coordinate_from_item(item: dict[str, object]) -> MavenCoordinate:
    if item.get("coordinate") is not None:
        return MavenCoordinate.from_string(str(item["coordinate"]))
    if item.get("gav") is not None:
        return MavenCoordinate.from_string(str(item["gav"]))

    group_id = item.get("group_id", item.get("groupId"))
    artifact_id = item.get("artifact_id", item.get("artifactId"))
    version = item.get("version")
    if group_id is None or artifact_id is None or version is None:
        raise ValueError("manifest item must contain `coordinate` / `gav` or `group_id`, `artifact_id`, and `version`")
    return MavenCoordinate(str(group_id), str(artifact_id), str(version))


def _normalize_item(
    item: object,
    *,
    defaults: dict[str, object] | None,
    source_path: str,
    item_index: int,
) -> WarmRequest:
    merged: dict[str, object]
    if isinstance(item, str):
        merged = {"coordinate": item}
    elif isinstance(item, dict):
        merged = dict(item)
    else:
        raise ValueError("manifest items must be strings or objects")

    if defaults:
        combined = dict(defaults)
        combined.update(merged)
        merged = combined

    coordinate = _coordinate_from_item(merged)
    return WarmRequest(
        coordinate=coordinate,
        include_version_metadata=_normalize_bool(merged.get("include_version_metadata"), default=True),
        source_type="manifest",
        source_path=source_path,
        source_line=item_index,
    )


class ManifestAdapter:
    def load(self, manifest_path: str) -> list[WarmRequest]:
        path = Path(manifest_path).expanduser().resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
        defaults: dict[str, object] | None = None

        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            defaults = dict(payload.get("defaults", {})) if isinstance(payload.get("defaults"), dict) else None
            if isinstance(payload.get("jobs"), list):
                items = payload["jobs"]
            elif isinstance(payload.get("coordinates"), list):
                items = payload["coordinates"]
            elif isinstance(payload.get("packages"), list):
                items = payload["packages"]
            else:
                raise ValueError("manifest must contain a top-level `jobs`, `coordinates`, or `packages` list")
        else:
            raise ValueError("manifest must be a JSON object or list")

        requests: list[WarmRequest] = []
        seen: set[str] = set()
        for item_index, item in enumerate(items, start=1):
            request = _normalize_item(item, defaults=defaults, source_path=str(path), item_index=item_index)
            if request.request_key in seen:
                continue
            seen.add(request.request_key)
            requests.append(request)

        if not requests:
            raise ValueError(f"manifest does not contain any Maven coordinates: {path}")
        return requests


__all__ = ["ManifestAdapter"]
