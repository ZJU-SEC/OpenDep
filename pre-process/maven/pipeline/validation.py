from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree


CURRENT_FILE = Path(__file__).resolve()
MAVEN_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]

for path in (MAVEN_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from adapters.package_list import MavenPackageSpec
from maven_models import WarmRequest
from pipeline.pom_fetcher import MetadataFetchError, MetadataNotFoundError, PomFetchError, PomNotFoundError


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, URLError):
        return True
    if isinstance(exc, HTTPError):
        status_code = getattr(exc, "code", None)
        return status_code not in {400, 401, 403, 404}
    if isinstance(exc, (PomNotFoundError, MetadataNotFoundError)):
        return False
    if isinstance(exc, (PomFetchError, MetadataFetchError)):
        return True
    return isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError)


class WarmValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class WarmValidationIssue:
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
class WarmFailureRecord:
    coordinate: str
    ga: str
    version: str | None
    stage: str
    error_type: str
    error_code: str
    error_message: str
    retryable: bool
    source_type: str
    source_path: str | None
    source_line: int | None
    metadata_strategy: str | None
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "coordinate": self.coordinate,
            "ga": self.ga,
            "version": self.version,
            "stage": self.stage,
            "error_type": self.error_type,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "retryable": self.retryable,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "source_line": self.source_line,
            "metadata_strategy": self.metadata_strategy,
            "created_at": self.created_at,
        }


def build_warning(code: str, message: str) -> WarmValidationIssue:
    return WarmValidationIssue(level="warning", code=code, message=message)


def _error_code_for(stage: str, exc: Exception) -> str:
    if isinstance(exc, WarmValidationError):
        return exc.code
    if isinstance(exc, PomNotFoundError):
        return "pom_not_found"
    if isinstance(exc, MetadataNotFoundError):
        return "metadata_not_found"
    if isinstance(exc, PomFetchError):
        return "pom_fetch_error"
    if isinstance(exc, MetadataFetchError):
        return "metadata_fetch_error"
    if stage == "prepare" and isinstance(exc, ValueError):
        return "invalid_request"
    if stage.startswith("write-") and isinstance(exc, OSError):
        return "repository_write_error"
    if stage.startswith("validate-"):
        return "invalid_xml"
    if isinstance(exc, OSError):
        return "io_error"
    return "unexpected_error"


def build_failure(
    request: WarmRequest,
    *,
    stage: str,
    exc: Exception,
    metadata_strategy: str | None = None,
) -> WarmFailureRecord:
    return WarmFailureRecord(
        coordinate=request.request_key,
        ga=request.coordinate.ga,
        version=request.coordinate.version,
        stage=stage,
        error_type=exc.__class__.__name__,
        error_code=_error_code_for(stage, exc),
        error_message=str(exc) or exc.__class__.__name__,
        retryable=is_retryable_exception(exc),
        source_type=request.source_type,
        source_path=request.source_path,
        source_line=request.source_line,
        metadata_strategy=metadata_strategy,
        created_at=utc_now_iso(),
    )


def build_package_failure(
    package: MavenPackageSpec,
    *,
    stage: str,
    exc: Exception,
) -> WarmFailureRecord:
    return WarmFailureRecord(
        coordinate=package.ga,
        ga=package.ga,
        version=None,
        stage=stage,
        error_type=exc.__class__.__name__,
        error_code=_error_code_for(stage, exc),
        error_message=str(exc) or exc.__class__.__name__,
        retryable=is_retryable_exception(exc),
        source_type=package.source_type,
        source_path=package.source_path,
        source_line=package.source_line,
        metadata_strategy=None,
        created_at=utc_now_iso(),
    )


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _validate_xml_payload(
    payload: bytes | str,
    *,
    expected_root: str,
    error_code: str,
    label: str,
) -> None:
    raw = payload if isinstance(payload, bytes) else payload.encode("utf-8")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise WarmValidationError(error_code, f"invalid {label} XML: {exc}") from exc

    actual_root = _local_name(root.tag)
    if actual_root != expected_root:
        raise WarmValidationError(
            error_code,
            f"invalid {label} XML root: expected `{expected_root}`, got `{actual_root}`",
        )


def validate_pom_payload(payload: bytes | str) -> None:
    _validate_xml_payload(
        payload,
        expected_root="project",
        error_code="invalid_pom_xml",
        label="POM",
    )


def validate_metadata_payload(payload: bytes | str) -> None:
    _validate_xml_payload(
        payload,
        expected_root="metadata",
        error_code="invalid_metadata_xml",
        label="metadata",
    )


__all__ = [
    "WarmFailureRecord",
    "WarmValidationError",
    "WarmValidationIssue",
    "build_failure",
    "build_package_failure",
    "build_warning",
    "is_retryable_exception",
    "utc_now_iso",
    "validate_metadata_payload",
    "validate_pom_payload",
]
