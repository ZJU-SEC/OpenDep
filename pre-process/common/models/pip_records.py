from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from resolving.containerization.images.pip.backend.models import PackageMetadataRecord


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dedupe(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


@dataclass(frozen=True, slots=True)
class ExtractionJob:
    artifact_path: str
    artifact_kind: str
    filename: str
    project_name: str | None = None
    version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_path": self.artifact_path,
            "artifact_kind": self.artifact_kind,
            "filename": self.filename,
            "project_name": self.project_name,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class BuildJobSpec:
    artifact_path: str
    project_name: str | None = None
    version: str | None = None
    artifact_url: str | None = None
    artifact_hash: str | None = None
    cleanup_artifact_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_path": self.artifact_path,
            "project_name": self.project_name,
            "version": self.version,
            "artifact_url": self.artifact_url,
            "artifact_hash": self.artifact_hash,
            "cleanup_artifact_path": self.cleanup_artifact_path,
        }


@dataclass(frozen=True, slots=True)
class BuildRequest:
    artifact_path: str | None = None
    project_name: str | None = None
    versions: tuple[str, ...] = ()
    limit: int | None = None
    include_yanked: bool = False
    mirror_dir: str | None = None

    @property
    def is_artifact(self) -> bool:
        return self.artifact_path is not None

    @property
    def is_package(self) -> bool:
        return self.project_name is not None and self.artifact_path is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_path": self.artifact_path,
            "project_name": self.project_name,
            "versions": list(self.versions),
            "limit": self.limit,
            "include_yanked": self.include_yanked,
            "mirror_dir": self.mirror_dir,
        }


@dataclass(frozen=True, slots=True)
class VersionPlanItem:
    project_name: str
    version: str
    yanked: bool = False
    source_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "version": self.version,
            "yanked": self.yanked,
            "source_kind": self.source_kind,
        }


@dataclass(frozen=True, slots=True)
class AcquiredArtifact:
    project_name: str
    version: str
    artifact_path: str
    artifact_url: str | None = None
    artifact_hash: str | None = None
    source_kind: str | None = None
    cleanup_artifact_path: str | None = None

    def to_build_job(self) -> BuildJobSpec:
        return BuildJobSpec(
            artifact_path=self.artifact_path,
            project_name=self.project_name,
            version=self.version,
            artifact_url=self.artifact_url,
            artifact_hash=self.artifact_hash,
            cleanup_artifact_path=self.cleanup_artifact_path,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "version": self.version,
            "artifact_path": self.artifact_path,
            "artifact_url": self.artifact_url,
            "artifact_hash": self.artifact_hash,
            "source_kind": self.source_kind,
            "cleanup_artifact_path": self.cleanup_artifact_path,
        }


@dataclass(frozen=True, slots=True)
class ExtractedMetadataRecord:
    name: str
    version: str
    requires_dist: tuple[str, ...] = ()
    requires_python: str | None = None
    yanked: bool = False
    source_kind: str = "unknown"
    artifact_path: str | None = None
    artifact_kind: str | None = None
    artifact_filename: str | None = None
    artifact_url: str | None = None
    artifact_hash: str | None = None
    dependency_source_detail: str | None = None
    parse_warnings: tuple[str, ...] = ()
    extracted_at: str | None = None
    extraction_backend: str = "preprocess-pip"

    @classmethod
    def from_package_metadata(
        cls,
        record: PackageMetadataRecord,
        *,
        artifact_path: str,
        artifact_kind: str,
        filename: str,
        extraction_backend: str,
        warning_prefix: str | None = None,
    ) -> "ExtractedMetadataRecord":
        warnings = list(record.parse_warnings)
        if warning_prefix:
            warnings.insert(0, warning_prefix)
        return cls(
            name=record.name,
            version=record.version,
            requires_dist=_dedupe(record.requires_dist),
            requires_python=record.requires_python,
            yanked=record.yanked,
            source_kind=record.source_kind,
            artifact_path=artifact_path,
            artifact_kind=artifact_kind,
            artifact_filename=filename,
            artifact_url=record.artifact_url,
            artifact_hash=record.artifact_hash,
            dependency_source_detail=record.dependency_source_detail,
            parse_warnings=tuple(warnings),
            extracted_at=record.extracted_at or utc_now_iso(),
            extraction_backend=extraction_backend,
        )

    def to_package_metadata(self) -> PackageMetadataRecord:
        return PackageMetadataRecord(
            name=self.name,
            version=self.version,
            requires_dist=self.requires_dist,
            requires_python=self.requires_python,
            yanked=self.yanked,
            source_kind=self.source_kind,
            artifact_url=self.artifact_url,
            artifact_hash=self.artifact_hash,
            extracted_at=self.extracted_at,
            dependency_source_detail=self.dependency_source_detail,
            parse_warnings=self.parse_warnings,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "requires_dist": list(self.requires_dist),
            "requires_python": self.requires_python,
            "yanked": self.yanked,
            "source_kind": self.source_kind,
            "artifact_path": self.artifact_path,
            "artifact_kind": self.artifact_kind,
            "artifact_filename": self.artifact_filename,
            "artifact_url": self.artifact_url,
            "artifact_hash": self.artifact_hash,
            "dependency_source_detail": self.dependency_source_detail,
            "parse_warnings": list(self.parse_warnings),
            "extracted_at": self.extracted_at,
            "extraction_backend": self.extraction_backend,
        }

    @property
    def dependency_count(self) -> int:
        return len(self.requires_dist)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    level: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ValidatedExtractionResult:
    status: str
    record: ExtractedMetadataRecord | None
    warnings: tuple[ValidationIssue, ...] = ()
    errors: tuple[ValidationIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status in {"ok", "partial"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "warnings": [item.to_dict() for item in self.warnings],
            "errors": [item.to_dict() for item in self.errors],
            "record": self.record.to_dict() if self.record is not None else None,
        }


@dataclass(frozen=True, slots=True)
class ExtractionFailureRecord:
    artifact_path: str
    artifact_filename: str
    artifact_kind: str | None
    project_name: str | None
    version: str | None
    stage: str
    error_type: str
    error_message: str
    retryable: bool
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_path": self.artifact_path,
            "artifact_filename": self.artifact_filename,
            "artifact_kind": self.artifact_kind,
            "project_name": self.project_name,
            "version": self.version,
            "stage": self.stage,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "retryable": self.retryable,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class BatchBuildItemResult:
    artifact_path: str | None
    status: str
    stage: str
    dependency_count: int = 0
    name: str | None = None
    version: str | None = None
    source_kind: str | None = None
    validation_status: str | None = None
    warning_count: int = 0
    error_count: int = 0
    failure: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_path": self.artifact_path,
            "status": self.status,
            "stage": self.stage,
            "dependency_count": self.dependency_count,
            "name": self.name,
            "version": self.version,
            "source_kind": self.source_kind,
            "validation_status": self.validation_status,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            "failure": self.failure,
        }


@dataclass(frozen=True, slots=True)
class BatchBuildSummary:
    status: str
    items: tuple[BatchBuildItemResult, ...]
    ensure_schema: bool
    table_name: str
    failure_log: str | None = None

    @property
    def loaded_count(self) -> int:
        return sum(1 for item in self.items if item.stage == "load" and item.status in {"ok", "partial"})

    @property
    def failed_count(self) -> int:
        return sum(1 for item in self.items if item.status == "error")

    @property
    def partial_count(self) -> int:
        return sum(1 for item in self.items if item.status == "partial")

    @property
    def skipped_count(self) -> int:
        return sum(1 for item in self.items if item.status == "skipped")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "operation": "batch-load",
            "items": [item.to_dict() for item in self.items],
            "metrics": {
                "requested_count": len(self.items),
                "loaded_count": self.loaded_count,
                "failed_count": self.failed_count,
                "partial_count": self.partial_count,
                "skipped_count": self.skipped_count,
            },
            "store": {
                "backend": "postgres",
                "table": self.table_name,
            },
            "ensure_schema": self.ensure_schema,
            "failure_log": self.failure_log,
        }


def artifact_filename(artifact_path: str) -> str:
    return Path(artifact_path).name


__all__ = [
    "BatchBuildItemResult",
    "BatchBuildSummary",
    "BuildRequest",
    "BuildJobSpec",
    "AcquiredArtifact",
    "ExtractedMetadataRecord",
    "ExtractionFailureRecord",
    "ExtractionJob",
    "VersionPlanItem",
    "ValidatedExtractionResult",
    "ValidationIssue",
    "artifact_filename",
    "utc_now_iso",
]
