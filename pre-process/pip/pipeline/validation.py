from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError

from pip_models import (
    ExtractedMetadataRecord,
    ExtractionFailureRecord,
    ValidatedExtractionResult,
    ValidationIssue,
    utc_now_iso,
)


def _normalize_messages(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def _normalize_dependencies(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, URLError):
        return True
    if isinstance(exc, HTTPError):
        status_code = getattr(exc, "code", None)
        return status_code not in {400, 401, 403, 404}
    return isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError)


class ExtractionQualityValidator:
    def validate(self, record: ExtractedMetadataRecord) -> ValidatedExtractionResult:
        warnings: list[ValidationIssue] = []
        errors: list[ValidationIssue] = []

        normalized_record = ExtractedMetadataRecord(
            name=record.name.strip(),
            version=record.version.strip(),
            requires_dist=_normalize_dependencies(record.requires_dist),
            requires_python=record.requires_python.strip() if isinstance(record.requires_python, str) else record.requires_python,
            yanked=record.yanked,
            source_kind=record.source_kind.strip(),
            artifact_path=record.artifact_path.strip() if isinstance(record.artifact_path, str) else record.artifact_path,
            artifact_kind=record.artifact_kind.strip() if isinstance(record.artifact_kind, str) else record.artifact_kind,
            artifact_filename=record.artifact_filename.strip() if isinstance(record.artifact_filename, str) else record.artifact_filename,
            dependency_source_detail=(
                record.dependency_source_detail.strip()
                if isinstance(record.dependency_source_detail, str)
                else record.dependency_source_detail
            ),
            parse_warnings=_normalize_messages(record.parse_warnings),
            extracted_at=record.extracted_at or utc_now_iso(),
            extraction_backend=record.extraction_backend.strip(),
        )

        if not normalized_record.name:
            errors.append(ValidationIssue("error", "missing_name", "extracted record did not contain a package name"))
        if not normalized_record.version:
            errors.append(ValidationIssue("error", "missing_version", "extracted record did not contain a version"))
        if not normalized_record.source_kind:
            errors.append(ValidationIssue("error", "missing_source_kind", "extracted record did not contain a source kind"))
        if not normalized_record.artifact_path:
            errors.append(ValidationIssue("error", "missing_artifact_path", "extracted record did not contain an artifact path"))
        if not normalized_record.artifact_filename:
            errors.append(
                ValidationIssue("error", "missing_artifact_filename", "extracted record did not contain an artifact filename")
            )

        if not normalized_record.requires_dist:
            warnings.append(ValidationIssue("warning", "no_dependencies", "package did not declare direct dependencies"))
        if normalized_record.parse_warnings:
            for item in normalized_record.parse_warnings:
                warnings.append(ValidationIssue("warning", "parse_warning", item))

        status = "error" if errors else "partial" if warnings else "ok"
        return ValidatedExtractionResult(
            status=status,
            record=None if errors else normalized_record,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    def build_failure(
        self,
        *,
        artifact_path: str,
        artifact_kind: str | None,
        project_name: str | None,
        version: str | None,
        stage: str,
        exc: Exception,
    ) -> ExtractionFailureRecord:
        return ExtractionFailureRecord(
            artifact_path=artifact_path,
            artifact_filename=Path(artifact_path).name,
            artifact_kind=artifact_kind,
            project_name=project_name,
            version=version,
            stage=stage,
            error_type=exc.__class__.__name__,
            error_message=str(exc) or exc.__class__.__name__,
            retryable=is_retryable_exception(exc),
            created_at=utc_now_iso(),
        )
