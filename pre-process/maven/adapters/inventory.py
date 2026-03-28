from __future__ import annotations

import gzip
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
        raise ValueError("inventory item must contain `coordinate` / `gav` or `group_id`, `artifact_id`, and `version`")
    return MavenCoordinate(str(group_id), str(artifact_id), str(version))


def _read_text(path: Path) -> str:
    if path.name.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return handle.read()
    return path.read_text(encoding="utf-8")


def _infer_inventory_format(path: Path) -> str:
    name = path.name.lower()
    if name.endswith((".jsonl", ".ndjson", ".jsonl.gz", ".ndjson.gz")):
        return "jsonl"
    if name.endswith((".json", ".json.gz")):
        return "json"
    return "text"


def _build_request(
    item: object,
    *,
    default_include_version_metadata: bool,
    source_path: str,
    source_line: int,
    source_type: str,
) -> WarmRequest:
    if isinstance(item, str):
        coordinate = MavenCoordinate.from_string(item)
        include_version_metadata = default_include_version_metadata
    elif isinstance(item, dict):
        coordinate = _coordinate_from_item(item)
        include_version_metadata = _normalize_bool(
            item.get("include_version_metadata"),
            default=default_include_version_metadata,
        )
    else:
        raise ValueError("inventory items must be strings or objects")

    return WarmRequest(
        coordinate=coordinate,
        include_version_metadata=include_version_metadata,
        source_type=source_type,
        source_path=source_path,
        source_line=source_line,
    )


class InventoryAdapter:
    def load(
        self,
        inventory_path: str,
        *,
        include_version_metadata: bool = True,
        source_type: str = "inventory-file",
    ) -> list[WarmRequest]:
        path = Path(inventory_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"inventory file does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"inventory file is not a file: {path}")

        file_format = _infer_inventory_format(path)
        if file_format == "json":
            return self._load_json(path, include_version_metadata=include_version_metadata, source_type=source_type)
        if file_format == "jsonl":
            return self._load_jsonl(path, include_version_metadata=include_version_metadata, source_type=source_type)
        return self._load_text(path, include_version_metadata=include_version_metadata, source_type=source_type)

    def _load_text(
        self,
        path: Path,
        *,
        include_version_metadata: bool,
        source_type: str,
    ) -> list[WarmRequest]:
        requests: list[WarmRequest] = []
        seen: set[str] = set()
        for line_number, raw_line in enumerate(_read_text(path).splitlines(), start=1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            request = _build_request(
                stripped,
                default_include_version_metadata=include_version_metadata,
                source_path=str(path),
                source_line=line_number,
                source_type=source_type,
            )
            if request.request_key in seen:
                continue
            seen.add(request.request_key)
            requests.append(request)

        if not requests:
            raise ValueError(f"inventory file does not contain any Maven coordinates: {path}")
        return requests

    def _load_json(
        self,
        path: Path,
        *,
        include_version_metadata: bool,
        source_type: str,
    ) -> list[WarmRequest]:
        payload = json.loads(_read_text(path))
        defaults: dict[str, object] | None = None
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            defaults = dict(payload.get("defaults", {})) if isinstance(payload.get("defaults"), dict) else None
            for key in ("jobs", "items", "coordinates", "gavs", "packages"):
                if isinstance(payload.get(key), list):
                    items = payload[key]
                    break
            else:
                raise ValueError("inventory JSON must contain a top-level `jobs`, `items`, `coordinates`, `gavs`, or `packages` list")
        else:
            raise ValueError("inventory JSON must be a JSON object or list")

        effective_default = include_version_metadata
        if defaults is not None:
            effective_default = _normalize_bool(defaults.get("include_version_metadata"), default=include_version_metadata)

        requests: list[WarmRequest] = []
        seen: set[str] = set()
        for item_index, item in enumerate(items, start=1):
            merged_item = item
            if isinstance(item, dict) and defaults:
                merged = dict(defaults)
                merged.update(item)
                merged_item = merged
            request = _build_request(
                merged_item,
                default_include_version_metadata=effective_default,
                source_path=str(path),
                source_line=item_index,
                source_type=source_type,
            )
            if request.request_key in seen:
                continue
            seen.add(request.request_key)
            requests.append(request)

        if not requests:
            raise ValueError(f"inventory file does not contain any Maven coordinates: {path}")
        return requests

    def _load_jsonl(
        self,
        path: Path,
        *,
        include_version_metadata: bool,
        source_type: str,
    ) -> list[WarmRequest]:
        requests: list[WarmRequest] = []
        seen: set[str] = set()
        for line_number, raw_line in enumerate(_read_text(path).splitlines(), start=1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            item = json.loads(stripped)
            request = _build_request(
                item,
                default_include_version_metadata=include_version_metadata,
                source_path=str(path),
                source_line=line_number,
                source_type=source_type,
            )
            if request.request_key in seen:
                continue
            seen.add(request.request_key)
            requests.append(request)

        if not requests:
            raise ValueError(f"inventory file does not contain any Maven coordinates: {path}")
        return requests


__all__ = ["InventoryAdapter"]
