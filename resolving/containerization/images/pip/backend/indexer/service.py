from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from packaging.utils import canonicalize_name
except ImportError:  # pragma: no cover - fallback for minimal pip environments
    from pip._vendor.packaging.utils import canonicalize_name

from resolving.containerization.images.pip.backend.errors import BackendError
from resolving.containerization.images.pip.backend.metadata_sources.base import MetadataSource
from resolving.containerization.images.pip.backend.models import VersionRecord
from resolving.containerization.images.pip.backend.stores.base import IndexStore


@dataclass(frozen=True, slots=True)
class IndexVersionResult:
    version: str
    status: str
    source_kind: str | None = None
    dependency_count: int = 0
    yanked: bool = False
    error: str | None = None
    backend_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "status": self.status,
            "source_kind": self.source_kind,
            "dependency_count": self.dependency_count,
            "yanked": self.yanked,
            "error": self.error,
            "backend_error": self.backend_error,
        }


@dataclass(frozen=True, slots=True)
class IndexingResult:
    project_name: str
    selected_versions: tuple[str, ...]
    versions: tuple[IndexVersionResult, ...]
    source_mode: str = "live"
    target_backend: str = "unknown"

    @property
    def indexed(self) -> tuple[IndexVersionResult, ...]:
        return tuple(item for item in self.versions if item.status == "indexed")

    @property
    def skipped(self) -> tuple[IndexVersionResult, ...]:
        return tuple(item for item in self.versions if item.status == "skipped")

    @property
    def failed(self) -> tuple[IndexVersionResult, ...]:
        return tuple(item for item in self.versions if item.status == "failed")

    @property
    def status(self) -> str:
        if not self.failed:
            return "ok"
        if not self.indexed and not self.skipped:
            return "error"
        return "partial"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "operation": "index",
            "project": self.project_name,
            "source_mode": self.source_mode,
            "target_backend": self.target_backend,
            "selected_versions": list(self.selected_versions),
            "versions": [item.to_dict() for item in self.versions],
            "metrics": {
                "selected_count": len(self.selected_versions),
                "attempted_count": len(self.versions),
                "indexed_count": len(self.indexed),
                "skipped_count": len(self.skipped),
                "failed_count": len(self.failed),
            },
        }


class IndexerService:
    def __init__(
        self,
        metadata_source: MetadataSource,
        store: IndexStore,
        *,
        target_backend: str = "unknown",
    ) -> None:
        self._metadata_source = metadata_source
        self._store = store
        self._target_backend = target_backend

    def index_project(
        self,
        project_name: str,
        *,
        versions: list[str] | tuple[str, ...] | None = None,
        include_yanked: bool = False,
        skip_existing: bool = False,
        fail_fast: bool = False,
        limit: int | None = None,
    ) -> IndexingResult:
        normalized_name = canonicalize_name(project_name)
        selected_records = self._select_versions(
            normalized_name,
            versions=versions,
            include_yanked=include_yanked,
            limit=limit,
        )

        results: list[IndexVersionResult] = []
        for selected in selected_records:
            if skip_existing:
                existing = self._store.get_release(normalized_name, selected.version)
                if existing is not None:
                    results.append(
                        IndexVersionResult(
                            version=selected.version,
                            status="skipped",
                            source_kind=existing.source_kind,
                            dependency_count=len(existing.requires_dist),
                            yanked=existing.yanked,
                        )
                    )
                    continue

            try:
                record = self._metadata_source.warm(normalized_name, selected.version)
                self._store.put_release(record)
            except Exception as exc:
                results.append(
                    IndexVersionResult(
                        version=selected.version,
                        status="failed",
                        yanked=selected.yanked,
                        error=str(exc) or exc.__class__.__name__,
                        backend_error=exc.__class__.__name__,
                    )
                )
                if fail_fast:
                    break
                continue

            results.append(
                IndexVersionResult(
                    version=record.version,
                    status="indexed",
                    source_kind=record.source_kind,
                    dependency_count=len(record.requires_dist),
                    yanked=record.yanked,
                )
            )

        return IndexingResult(
            project_name=normalized_name,
            selected_versions=tuple(item.version for item in selected_records),
            versions=tuple(results),
            source_mode=getattr(self._metadata_source, "mode_name", "live"),
            target_backend=self._target_backend,
        )

    def _select_versions(
        self,
        project_name: str,
        *,
        versions: list[str] | tuple[str, ...] | None,
        include_yanked: bool,
        limit: int | None,
    ) -> list[VersionRecord]:
        if limit is not None and limit <= 0:
            raise BackendError(
                "INVALID_ARGUMENT",
                "index limit must be greater than zero",
                retryable=False,
            )

        if versions:
            ordered_versions: list[str] = []
            seen_versions: set[str] = set()
            for version in versions:
                normalized_version = version.strip()
                if not normalized_version or normalized_version in seen_versions:
                    continue
                seen_versions.add(normalized_version)
                ordered_versions.append(normalized_version)
            if not ordered_versions:
                raise BackendError(
                    "INVALID_ARGUMENT",
                    "at least one non-empty version must be provided",
                    retryable=False,
                )
            return [
                VersionRecord(
                    name=project_name,
                    version=version,
                    source_kind=getattr(self._metadata_source, "mode_name", "live"),
                )
                for version in ordered_versions
            ]

        available_versions = self._metadata_source.list_versions(project_name)
        if not available_versions:
            raise BackendError(
                "PACKAGE_NOT_FOUND",
                f"package `{project_name}` was not found",
                retryable=False,
            )

        selected = available_versions
        if not include_yanked:
            non_yanked = [item for item in available_versions if not item.yanked]
            if non_yanked:
                selected = non_yanked

        if limit is not None:
            selected = selected[:limit]

        return selected
