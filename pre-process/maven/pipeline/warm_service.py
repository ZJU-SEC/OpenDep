from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
MAVEN_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]
COMMON_UTILS_ROOT = PROJECT_ROOT / "pre-process" / "common" / "utils"

for path in (MAVEN_ROOT, PROJECT_ROOT, COMMON_UTILS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from logging_utils import get_logger
from maven_models import LocalRepositoryLayout, MavenCoordinate, WarmRequest
from loaders.repository_compat import (
    RepositoryCleanupResult,
    cleanup_artifact_tracking_files,
    cleanup_metadata_tracking_files,
)
from loaders.repository_layout import build_repository_layout
from loaders.repository_writer import metadata_exists, pom_exists, write_metadata_file, write_pom_file
from pipeline.pom_fetcher import MavenPomFetcher, build_metadata_url, build_pom_url
from pipeline.validation import (
    WarmFailureRecord,
    WarmValidationIssue,
    build_failure,
    build_warning,
    validate_metadata_payload,
    validate_pom_payload,
)
from pipeline.version_metadata import VersionMetadataPlan, build_version_metadata_plan


def _payload_from_path(path: str) -> bytes:
    return Path(path).read_bytes()


def _normalize_request(request: WarmRequest | MavenCoordinate | str) -> WarmRequest:
    if isinstance(request, WarmRequest):
        return request
    coordinate = request if isinstance(request, MavenCoordinate) else MavenCoordinate.from_string(str(request))
    return WarmRequest(coordinate=coordinate)


@dataclass(frozen=True, slots=True)
class MetadataWarmResult:
    strategy: str
    status: str
    required: bool
    supported: bool
    path: str | None
    url: str | None
    bytes_written: int
    reason: str
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class WarmResult:
    request: WarmRequest
    layout: LocalRepositoryLayout
    pom_path: str | None
    pom_url: str | None
    status: str
    bytes_written: int
    metadata_result: MetadataWarmResult
    cleanup_result: RepositoryCleanupResult | None = None
    warnings: tuple[WarmValidationIssue, ...] = ()
    failure: WarmFailureRecord | None = None
    warning_message: str | None = None


def _metadata_result_for_plan(
    plan: VersionMetadataPlan,
    *,
    status: str,
    layout: LocalRepositoryLayout,
    url: str | None = None,
    bytes_written: int = 0,
    error_message: str | None = None,
) -> MetadataWarmResult:
    return MetadataWarmResult(
        strategy=plan.strategy,
        status=status,
        required=plan.required,
        supported=plan.supported,
        path=layout.metadata_path if plan.required and plan.supported else None,
        url=url,
        bytes_written=bytes_written,
        reason=plan.reason,
        error_message=error_message,
    )


class MavenWarmService:
    def __init__(
        self,
        *,
        pom_fetcher: MavenPomFetcher | None = None,
        logger=None,
    ) -> None:
        self._pom_fetcher = pom_fetcher or MavenPomFetcher()
        self._logger = logger or get_logger("preprocess.maven.warm")

    def _cleanup_artifact(self, request: WarmRequest, *, repository_root: str | None) -> RepositoryCleanupResult:
        result = cleanup_artifact_tracking_files(request.coordinate, repository_root=repository_root)
        if result.removed_count:
            self._logger.info("Removed %s artifact tracking file(s) for %s", result.removed_count, request.request_key)
        return result

    def _cleanup_metadata(self, request: WarmRequest, *, repository_root: str | None) -> RepositoryCleanupResult:
        result = cleanup_metadata_tracking_files(request.coordinate, repository_root=repository_root)
        if result.removed_count:
            self._logger.info("Removed %s metadata tracking file(s) for %s", result.removed_count, request.request_key)
        return result

    def _can_skip_existing_metadata(self, request: WarmRequest, *, layout: LocalRepositoryLayout) -> bool:
        if not metadata_exists(request.coordinate, repository_root=layout.repository_root):
            return False
        try:
            validate_metadata_payload(_payload_from_path(layout.metadata_path))
        except Exception as exc:
            self._logger.warning(
                "Existing Maven metadata for %s is invalid and will be refreshed: %s",
                request.request_key,
                exc,
            )
            return False
        return True

    def _can_skip_existing_pom(self, request: WarmRequest, *, layout: LocalRepositoryLayout) -> bool:
        if not pom_exists(request.coordinate, repository_root=layout.repository_root):
            return False
        try:
            validate_pom_payload(_payload_from_path(layout.pom_path))
        except Exception as exc:
            self._logger.warning(
                "Existing Maven POM for %s is invalid and will be refreshed: %s",
                request.request_key,
                exc,
            )
            return False
        return True

    def warm_request(
        self,
        request: WarmRequest | MavenCoordinate | str,
        *,
        repository_root: str | None = None,
        skip_existing: bool = False,
    ) -> WarmResult:
        resolved_request = _normalize_request(request)
        layout = build_repository_layout(resolved_request.coordinate, repository_root=repository_root)
        metadata_plan = build_version_metadata_plan(
            resolved_request.coordinate.version,
            include_version_metadata=resolved_request.include_version_metadata,
        )

        if not metadata_plan.direct_pom_fetch:
            metadata_build_url = getattr(self._pom_fetcher, "build_metadata_url", build_metadata_url)
            metadata_url = metadata_build_url(resolved_request.coordinate) if metadata_plan.supported else None
            warnings = (build_warning("metadata_only_warm", metadata_plan.reason),)

            if not metadata_plan.supported:
                self._logger.warning(
                    "Metadata warming for %s is not fully supported: %s",
                    resolved_request.coordinate.gav,
                    metadata_plan.reason,
                )
                return WarmResult(
                    request=resolved_request,
                    layout=layout,
                    pom_path=None,
                    pom_url=None,
                    status="partial",
                    bytes_written=0,
                    metadata_result=_metadata_result_for_plan(
                        metadata_plan,
                        status="unsupported",
                        layout=layout,
                        url=metadata_url,
                    ),
                    warnings=(build_warning("unsupported_metadata_strategy", metadata_plan.reason),),
                    warning_message=metadata_plan.reason,
                )

            if skip_existing and self._can_skip_existing_metadata(resolved_request, layout=layout):
                cleanup_result = self._cleanup_metadata(resolved_request, repository_root=repository_root)
                return WarmResult(
                    request=resolved_request,
                    layout=layout,
                    pom_path=None,
                    pom_url=None,
                    status="partial",
                    bytes_written=0,
                    metadata_result=_metadata_result_for_plan(
                        metadata_plan,
                        status="skipped",
                        layout=layout,
                        url=metadata_url,
                    ),
                    cleanup_result=cleanup_result,
                    warnings=warnings,
                    warning_message=metadata_plan.reason,
                )

            try:
                metadata_payload = self._pom_fetcher.fetch_metadata_bytes(resolved_request.coordinate)
            except Exception as exc:
                failure = build_failure(
                    resolved_request,
                    stage="fetch-metadata",
                    exc=exc,
                    metadata_strategy=metadata_plan.strategy,
                )
                self._logger.error("Failed to warm Maven metadata for %s: %s", resolved_request.coordinate.gav, exc)
                return WarmResult(
                    request=resolved_request,
                    layout=layout,
                    pom_path=None,
                    pom_url=None,
                    status="error",
                    bytes_written=0,
                    metadata_result=_metadata_result_for_plan(
                        metadata_plan,
                        status="error",
                        layout=layout,
                        url=metadata_url,
                        error_message=str(exc),
                    ),
                    warnings=warnings,
                    failure=failure,
                    warning_message=metadata_plan.reason,
                )

            try:
                validate_metadata_payload(metadata_payload)
            except Exception as exc:
                failure = build_failure(
                    resolved_request,
                    stage="validate-metadata",
                    exc=exc,
                    metadata_strategy=metadata_plan.strategy,
                )
                self._logger.error("Failed to warm Maven metadata for %s: %s", resolved_request.coordinate.gav, exc)
                return WarmResult(
                    request=resolved_request,
                    layout=layout,
                    pom_path=None,
                    pom_url=None,
                    status="error",
                    bytes_written=0,
                    metadata_result=_metadata_result_for_plan(
                        metadata_plan,
                        status="error",
                        layout=layout,
                        url=metadata_url,
                        error_message=str(exc),
                    ),
                    warnings=warnings,
                    failure=failure,
                    warning_message=metadata_plan.reason,
                )

            try:
                write_result = write_metadata_file(
                    resolved_request.coordinate,
                    metadata_payload,
                    repository_root=repository_root,
                )
                cleanup_result = self._cleanup_metadata(resolved_request, repository_root=repository_root)
            except Exception as exc:
                failure = build_failure(
                    resolved_request,
                    stage="write-metadata",
                    exc=exc,
                    metadata_strategy=metadata_plan.strategy,
                )
                self._logger.error("Failed to write Maven metadata for %s: %s", resolved_request.coordinate.gav, exc)
                return WarmResult(
                    request=resolved_request,
                    layout=layout,
                    pom_path=None,
                    pom_url=None,
                    status="error",
                    bytes_written=0,
                    metadata_result=_metadata_result_for_plan(
                        metadata_plan,
                        status="error",
                        layout=layout,
                        url=metadata_url,
                        error_message=str(exc),
                    ),
                    warnings=warnings,
                    failure=failure,
                    warning_message=metadata_plan.reason,
                )

            metadata_status = "updated" if write_result.existed_before_write else "fetched"
            self._logger.info(
                "Warmed Maven metadata for %s into %s",
                resolved_request.coordinate.ga,
                write_result.layout.metadata_path,
            )
            return WarmResult(
                request=resolved_request,
                layout=layout,
                pom_path=None,
                pom_url=None,
                status="partial",
                bytes_written=0,
                metadata_result=_metadata_result_for_plan(
                    metadata_plan,
                    status=metadata_status,
                    layout=write_result.layout,
                    url=metadata_url,
                    bytes_written=write_result.bytes_written,
                ),
                cleanup_result=cleanup_result,
                warnings=warnings,
                warning_message=metadata_plan.reason,
            )

        build_url = getattr(self._pom_fetcher, "build_url", build_pom_url)
        pom_url = build_url(resolved_request.coordinate)

        if skip_existing and self._can_skip_existing_pom(resolved_request, layout=layout):
            self._logger.info("Skipping existing Maven POM for %s at %s", resolved_request.coordinate.gav, layout.pom_path)
            cleanup_result = self._cleanup_artifact(resolved_request, repository_root=repository_root)
            return WarmResult(
                request=resolved_request,
                layout=layout,
                pom_path=layout.pom_path,
                pom_url=pom_url,
                status="skipped",
                bytes_written=0,
                metadata_result=_metadata_result_for_plan(
                    metadata_plan,
                    status="disabled" if metadata_plan.strategy == "disabled" else "not-needed",
                    layout=layout,
                ),
                cleanup_result=cleanup_result,
            )

        try:
            pom_payload = self._pom_fetcher.fetch_bytes(resolved_request.coordinate)
        except Exception as exc:
            failure = build_failure(
                resolved_request,
                stage="fetch-pom",
                exc=exc,
                metadata_strategy=metadata_plan.strategy,
            )
            self._logger.error("Failed to fetch Maven POM for %s: %s", resolved_request.coordinate.gav, exc)
            return WarmResult(
                request=resolved_request,
                layout=layout,
                pom_path=None,
                pom_url=pom_url,
                status="error",
                bytes_written=0,
                metadata_result=_metadata_result_for_plan(
                    metadata_plan,
                    status="disabled" if metadata_plan.strategy == "disabled" else "not-needed",
                    layout=layout,
                ),
                failure=failure,
            )

        try:
            validate_pom_payload(pom_payload)
        except Exception as exc:
            failure = build_failure(
                resolved_request,
                stage="validate-pom",
                exc=exc,
                metadata_strategy=metadata_plan.strategy,
            )
            self._logger.error("Failed to validate Maven POM for %s: %s", resolved_request.coordinate.gav, exc)
            return WarmResult(
                request=resolved_request,
                layout=layout,
                pom_path=None,
                pom_url=pom_url,
                status="error",
                bytes_written=0,
                metadata_result=_metadata_result_for_plan(
                    metadata_plan,
                    status="disabled" if metadata_plan.strategy == "disabled" else "not-needed",
                    layout=layout,
                ),
                failure=failure,
            )

        try:
            write_result = write_pom_file(
                resolved_request.coordinate,
                pom_payload,
                repository_root=repository_root,
            )
            cleanup_result = self._cleanup_artifact(resolved_request, repository_root=repository_root)
        except Exception as exc:
            failure = build_failure(
                resolved_request,
                stage="write-pom",
                exc=exc,
                metadata_strategy=metadata_plan.strategy,
            )
            self._logger.error("Failed to write Maven POM for %s: %s", resolved_request.coordinate.gav, exc)
            return WarmResult(
                request=resolved_request,
                layout=layout,
                pom_path=None,
                pom_url=pom_url,
                status="error",
                bytes_written=0,
                metadata_result=_metadata_result_for_plan(
                    metadata_plan,
                    status="disabled" if metadata_plan.strategy == "disabled" else "not-needed",
                    layout=layout,
                ),
                failure=failure,
            )

        status = "updated" if write_result.existed_before_write else "fetched"
        self._logger.info("Warmed Maven POM for %s into %s", resolved_request.coordinate.gav, write_result.layout.pom_path)
        return WarmResult(
            request=resolved_request,
            layout=write_result.layout,
            pom_path=write_result.layout.pom_path,
            pom_url=pom_url,
            status=status,
            bytes_written=write_result.bytes_written,
            metadata_result=_metadata_result_for_plan(
                metadata_plan,
                status="disabled" if metadata_plan.strategy == "disabled" else "not-needed",
                layout=write_result.layout,
            ),
            cleanup_result=cleanup_result,
        )


__all__ = [
    "MetadataWarmResult",
    "MavenWarmService",
    "WarmResult",
]
