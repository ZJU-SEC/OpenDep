from __future__ import annotations

from pathlib import Path
import sys

try:
    from packaging.utils import canonicalize_name
except ImportError:  # pragma: no cover
    from pip._vendor.packaging.utils import canonicalize_name


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from pip_models import BuildRequest, VersionPlanItem


class VersionPlanner:
    def __init__(self, version_source) -> None:
        self._version_source = version_source

    def plan(self, request: BuildRequest) -> list[VersionPlanItem]:
        if not request.is_package or not request.project_name:
            raise ValueError("version planning requires a package build request")

        normalized_name = canonicalize_name(request.project_name)
        if request.limit is not None and request.limit <= 0:
            raise ValueError("index limit must be greater than zero")

        if request.versions:
            ordered_versions: list[str] = []
            seen_versions: set[str] = set()
            for version in request.versions:
                normalized_version = version.strip()
                if not normalized_version or normalized_version in seen_versions:
                    continue
                seen_versions.add(normalized_version)
                ordered_versions.append(normalized_version)
            if not ordered_versions:
                raise ValueError("at least one non-empty version must be provided")
            return [
                VersionPlanItem(
                    project_name=normalized_name,
                    version=version,
                    yanked=False,
                    source_kind="planned-explicit",
                )
                for version in ordered_versions
            ]

        available_versions = self._version_source.list_versions(normalized_name)
        if not available_versions:
            raise ValueError(f"package `{normalized_name}` was not found")

        selected = available_versions
        if not request.include_yanked:
            non_yanked = [item for item in available_versions if not item.yanked]
            if non_yanked:
                selected = non_yanked

        if request.limit is not None:
            selected = selected[: request.limit]

        return [
            VersionPlanItem(
                project_name=normalized_name,
                version=item.version,
                yanked=item.yanked,
                source_kind=item.source_kind,
            )
            for item in selected
        ]


__all__ = ["VersionPlanner"]
