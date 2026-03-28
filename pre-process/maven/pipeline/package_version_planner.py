from __future__ import annotations

from pathlib import Path
import sys
from dataclasses import dataclass
from xml.etree import ElementTree


CURRENT_FILE = Path(__file__).resolve()
MAVEN_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]

for path in (MAVEN_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from adapters.package_list import MavenPackageSpec
from maven_models import MavenCoordinate, WarmRequest
from pipeline.pom_fetcher import MetadataFetchError, MetadataNotFoundError, MavenPomFetcher
from pipeline.validation import WarmFailureRecord, WarmValidationError, build_package_failure, validate_metadata_payload


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _first_child(element: ElementTree.Element, name: str) -> ElementTree.Element | None:
    for child in element:
        if _local_name(child.tag) == name:
            return child
    return None


def parse_metadata_versions(payload: bytes | str, *, package_name: str) -> list[str]:
    validate_metadata_payload(payload)
    raw = payload if isinstance(payload, bytes) else payload.encode("utf-8")
    root = ElementTree.fromstring(raw)

    metadata_group_id = _first_child(root, "groupId")
    metadata_artifact_id = _first_child(root, "artifactId")
    declared_ga = ":".join(
        part
        for part in (
            (metadata_group_id.text or "").strip() if metadata_group_id is not None and metadata_group_id.text else "",
            (metadata_artifact_id.text or "").strip() if metadata_artifact_id is not None and metadata_artifact_id.text else "",
        )
        if part
    )
    if declared_ga and declared_ga != package_name:
        raise ValueError(
            f"metadata package mismatch: expected `{package_name}`, got `{declared_ga}`"
        )

    versioning = _first_child(root, "versioning")
    if versioning is None:
        raise ValueError(f"Maven metadata for `{package_name}` does not contain a `versioning` section")

    versions_parent = _first_child(versioning, "versions")
    ordered_versions: list[str] = []
    seen_versions: set[str] = set()

    if versions_parent is not None:
        for child in versions_parent:
            if _local_name(child.tag) != "version":
                continue
            normalized_version = (child.text or "").strip()
            if not normalized_version or normalized_version in seen_versions:
                continue
            seen_versions.add(normalized_version)
            ordered_versions.append(normalized_version)

    if not ordered_versions:
        for fallback_name in ("release", "latest"):
            fallback_node = _first_child(versioning, fallback_name)
            normalized_version = (fallback_node.text or "").strip() if fallback_node is not None and fallback_node.text else ""
            if not normalized_version or normalized_version in seen_versions:
                continue
            seen_versions.add(normalized_version)
            ordered_versions.append(normalized_version)

    if not ordered_versions:
        raise ValueError(f"Maven metadata for `{package_name}` does not contain any versions")

    return ordered_versions


def _planning_stage_for_exception(exc: Exception) -> str:
    if isinstance(exc, (MetadataFetchError, MetadataNotFoundError)):
        return "plan-fetch-metadata"
    if isinstance(exc, WarmValidationError):
        return "plan-parse-metadata"
    if isinstance(exc, ValueError):
        return "plan-package"
    return "plan-package"


@dataclass(frozen=True, slots=True)
class PackageVersionPlanningResult:
    requests: tuple[WarmRequest, ...]
    failures: tuple[WarmFailureRecord, ...] = ()

    @property
    def failure_count(self) -> int:
        return len(self.failures)


class MavenPackageVersionPlanner:
    def __init__(self, *, fetcher: MavenPomFetcher | None = None) -> None:
        self._fetcher = fetcher or MavenPomFetcher()

    def plan(
        self,
        package: MavenPackageSpec,
        *,
        include_version_metadata: bool = True,
    ) -> list[WarmRequest]:
        metadata_payload = self._fetcher.fetch_package_metadata_bytes(
            package.group_id,
            package.artifact_id,
        )
        versions = parse_metadata_versions(metadata_payload, package_name=package.ga)
        return [
            WarmRequest(
                coordinate=MavenCoordinate(package.group_id, package.artifact_id, version),
                include_version_metadata=include_version_metadata,
                source_type=package.source_type,
                source_path=package.source_path,
                source_line=package.source_line,
            )
            for version in versions
        ]

    def plan_all(
        self,
        packages: list[MavenPackageSpec],
        *,
        include_version_metadata: bool = True,
        fail_fast: bool = False,
    ) -> PackageVersionPlanningResult:
        requests: list[WarmRequest] = []
        seen: set[str] = set()
        failures: list[WarmFailureRecord] = []
        for package in packages:
            try:
                planned_requests = self.plan(package, include_version_metadata=include_version_metadata)
            except Exception as exc:
                failures.append(
                    build_package_failure(
                        package,
                        stage=_planning_stage_for_exception(exc),
                        exc=exc,
                    )
                )
                if fail_fast:
                    break
                continue

            for request in planned_requests:
                if request.request_key in seen:
                    continue
                seen.add(request.request_key)
                requests.append(request)
        return PackageVersionPlanningResult(
            requests=tuple(requests),
            failures=tuple(failures),
        )


__all__ = [
    "MavenPackageVersionPlanner",
    "PackageVersionPlanningResult",
    "parse_metadata_versions",
]
