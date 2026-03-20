from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable
from urllib.request import Request, urlopen

try:
    from packaging.utils import canonicalize_name
except ImportError:  # pragma: no cover - fallback for minimal pip environments
    from pip._vendor.packaging.utils import canonicalize_name

from Resolver.containerization.images.pip.backend.inspectors import (
    SdistDependencyInspector,
    WheelDependencyInspector,
)
from Resolver.containerization.images.pip.backend.inspectors.selector import (
    ArtifactReference,
    select_preferred_artifacts,
)
from Resolver.containerization.images.pip.backend.metadata_sources.base import MetadataSource
from Resolver.containerization.images.pip.backend.models import PackageMetadataRecord, VersionRecord


JsonFetcher = Callable[[str], dict[str, Any]]
ArtifactDownloader = Callable[[ArtifactReference], str]


class LiveMetadataSource(MetadataSource):
    mode_name = "live"

    def __init__(
        self,
        *,
        cache_dir: str | None = None,
        pypi_json_base_url: str = "https://pypi.org/pypi",
        http_user_agent: str = "OpenDep-Pip-Resolver/0.1",
        json_fetcher: JsonFetcher | None = None,
        artifact_downloader: ArtifactDownloader | None = None,
    ) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._pypi_json_base_url = pypi_json_base_url.rstrip("/")
        self._http_user_agent = http_user_agent
        self._json_fetcher = json_fetcher or self._fetch_json
        self._artifact_downloader = artifact_downloader or self._download_artifact
        self._wheel_inspector = WheelDependencyInspector()
        self._sdist_inspector = SdistDependencyInspector()

    def list_versions(self, project_name: str) -> list[VersionRecord]:
        normalized_name = canonicalize_name(project_name)
        cached = self._load_cached_versions(normalized_name)
        if cached is not None:
            return cached

        payload = self._json_fetcher(f"{self._pypi_json_base_url}/{normalized_name}/json")
        records: list[VersionRecord] = []
        releases = payload.get("releases", {})
        if isinstance(releases, dict):
            for version, files in releases.items():
                yanked = False
                if isinstance(files, list) and files:
                    yanked = all(bool(entry.get("yanked", False)) for entry in files if isinstance(entry, dict))
                records.append(
                    VersionRecord(
                        name=payload.get("info", {}).get("name") or normalized_name,
                        version=str(version),
                        yanked=yanked,
                        source_kind="live-index",
                    )
                )

        sorted_records = self._sort_versions(records)
        self._store_versions_cache(normalized_name, sorted_records)
        return sorted_records

    def get_release(self, project_name: str, version: str) -> PackageMetadataRecord | None:
        return self._load_cached_release(canonicalize_name(project_name), version)

    def warm(self, project_name: str, version: str) -> PackageMetadataRecord:
        normalized_name = canonicalize_name(project_name)
        cached = self._load_cached_release(normalized_name, version)
        if cached is not None:
            return cached

        payload = self._json_fetcher(f"{self._pypi_json_base_url}/{normalized_name}/{version}/json")
        info = payload.get("info", {}) if isinstance(payload.get("info"), dict) else {}
        display_name = info.get("name") or normalized_name
        artifact = self._select_artifact(payload)
        artifact_path = self._artifact_downloader(artifact)

        if artifact.kind == "wheel":
            inspected = self._wheel_inspector.inspect_distribution(
                artifact_path,
                project_name=display_name,
                version=version,
            )
        else:
            inspected = self._sdist_inspector.inspect_distribution(
                artifact_path,
                project_name=display_name,
                version=version,
            )

        record = PackageMetadataRecord(
            name=inspected.name,
            version=inspected.version,
            requires_dist=inspected.requires_dist,
            requires_python=inspected.requires_python or info.get("requires_python"),
            yanked=artifact.yanked,
            source_kind=inspected.source_kind,
            artifact_url=artifact.url,
            artifact_hash=self._artifact_hash(artifact),
            extracted_at=self._timestamp(),
            dependency_source_detail=inspected.dependency_source_detail,
            parse_warnings=inspected.parse_warnings,
        )
        self._store_release_cache(normalized_name, version, record)
        return record

    def _select_artifact(self, payload: dict[str, Any]) -> ArtifactReference:
        urls = payload.get("urls", [])
        artifacts = [
            ArtifactReference.from_pypi_file(item)
            for item in urls
            if isinstance(item, dict)
        ]
        selected = select_preferred_artifacts(artifacts)
        if not selected:
            raise ValueError("no supported artifacts available for requested release")
        return selected[0]

    def _fetch_json(self, url: str) -> dict[str, Any]:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": self._http_user_agent,
            },
        )
        with urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    def _download_artifact(self, artifact: ArtifactReference) -> str:
        if artifact.url is None:
            raise ValueError("artifact url is required for live downloads")

        destination = self._artifact_cache_path(artifact)
        if destination is not None and destination.exists():
            return str(destination)

        request = Request(artifact.url, headers={"User-Agent": self._http_user_agent})
        with urlopen(request) as response:
            if destination is None:
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(artifact.filename).suffix) as temp_file:
                    shutil.copyfileobj(response, temp_file)
                    return temp_file.name

            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output)
            return str(destination)

    def _artifact_hash(self, artifact: ArtifactReference) -> str | None:
        if not artifact.hashes:
            return None
        sha256 = artifact.hashes.get("sha256")
        if sha256:
            return f"sha256:{sha256}"
        for algorithm, digest in artifact.hashes.items():
            return f"{algorithm}:{digest}"
        return None

    def _cache_path(self, *parts: str) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir.joinpath(*parts)

    def _artifact_cache_path(self, artifact: ArtifactReference) -> Path | None:
        if self._cache_dir is None:
            return None
        unique = hashlib.sha256((artifact.url or artifact.filename).encode("utf-8")).hexdigest()[:16]
        safe_filename = Path(artifact.filename).name
        return self._cache_path("artifacts", f"{unique}-{safe_filename}")

    def _load_cached_versions(self, project_name: str) -> list[VersionRecord] | None:
        path = self._cache_path("versions", f"{project_name}.json")
        if path is None or not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return None
        return [
            VersionRecord(
                name=str(item["name"]),
                version=str(item["version"]),
                yanked=bool(item.get("yanked", False)),
                source_kind=str(item["source_kind"]) if item.get("source_kind") else None,
            )
            for item in payload
            if isinstance(item, dict) and item.get("version")
        ]

    def _store_versions_cache(self, project_name: str, versions: list[VersionRecord]) -> None:
        path = self._cache_path("versions", f"{project_name}.json")
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [record.to_dict() for record in versions]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_cached_release(self, project_name: str, version: str) -> PackageMetadataRecord | None:
        path = self._cache_path("releases", project_name, f"{version}.json")
        if path is None or not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        return PackageMetadataRecord(
            name=str(payload["name"]),
            version=str(payload["version"]),
            requires_dist=tuple(str(item) for item in payload.get("requires_dist", [])),
            requires_python=str(payload["requires_python"]) if payload.get("requires_python") is not None else None,
            yanked=bool(payload.get("yanked", False)),
            source_kind=str(payload.get("source_kind") or "live-cache"),
            artifact_url=str(payload["artifact_url"]) if payload.get("artifact_url") is not None else None,
            artifact_hash=str(payload["artifact_hash"]) if payload.get("artifact_hash") is not None else None,
            extracted_at=str(payload["extracted_at"]) if payload.get("extracted_at") is not None else None,
            dependency_source_detail=(
                str(payload["dependency_source_detail"])
                if payload.get("dependency_source_detail") is not None
                else None
            ),
            parse_warnings=tuple(str(item) for item in payload.get("parse_warnings", [])),
        )

    def _store_release_cache(self, project_name: str, version: str, record: PackageMetadataRecord) -> None:
        path = self._cache_path("releases", project_name, f"{version}.json")
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _sort_versions(self, versions: list[VersionRecord]) -> list[VersionRecord]:
        try:
            from packaging.version import InvalidVersion, Version
        except ImportError:  # pragma: no cover - fallback for minimal pip environments
            from pip._vendor.packaging.version import InvalidVersion, Version

        def sort_key(record: VersionRecord):
            try:
                return (1, Version(record.version))
            except InvalidVersion:
                return (0, record.version)

        return sorted(versions, key=sort_key, reverse=True)

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
