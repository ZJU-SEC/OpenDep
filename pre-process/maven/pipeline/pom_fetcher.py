from __future__ import annotations

from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CURRENT_FILE = Path(__file__).resolve()
MAVEN_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]
COMMON_UTILS_ROOT = PROJECT_ROOT / "pre-process" / "common" / "utils"

for path in (MAVEN_ROOT, PROJECT_ROOT, COMMON_UTILS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from logging_utils import get_logger
from maven_models import MavenCoordinate
from retry import RetrySettings, run_with_retry


DEFAULT_MAVEN_CENTRAL_BASE_URL = "https://repo.maven.apache.org/maven2"


class PomFetchError(RuntimeError):
    """Raised when a remote POM cannot be fetched successfully."""


class PomNotFoundError(PomFetchError):
    """Raised when the remote repository returns 404 for a POM."""


class MetadataFetchError(RuntimeError):
    """Raised when repository metadata cannot be fetched successfully."""


class MetadataNotFoundError(MetadataFetchError):
    """Raised when the remote repository returns 404 for Maven metadata."""


def _normalize_coordinate(coordinate: MavenCoordinate | str) -> MavenCoordinate:
    if isinstance(coordinate, MavenCoordinate):
        return coordinate
    return MavenCoordinate.from_string(str(coordinate))


def build_pom_url(
    coordinate: MavenCoordinate | str,
    *,
    base_url: str = DEFAULT_MAVEN_CENTRAL_BASE_URL,
) -> str:
    resolved_coordinate = _normalize_coordinate(coordinate)
    normalized_base_url = base_url.rstrip("/")
    return (
        f"{normalized_base_url}/"
        f"{resolved_coordinate.artifact_directory}/"
        f"{resolved_coordinate.artifact_filename('pom')}"
    )


def build_metadata_url(
    coordinate: MavenCoordinate | str,
    *,
    base_url: str = DEFAULT_MAVEN_CENTRAL_BASE_URL,
) -> str:
    resolved_coordinate = _normalize_coordinate(coordinate)
    normalized_base_url = base_url.rstrip("/")
    return (
        f"{normalized_base_url}/"
        f"{resolved_coordinate.group_path}/"
        f"{resolved_coordinate.artifact_id}/"
        "maven-metadata.xml"
    )


def build_package_metadata_url(
    group_id: str,
    artifact_id: str,
    *,
    base_url: str = DEFAULT_MAVEN_CENTRAL_BASE_URL,
) -> str:
    normalized_group_id = group_id.strip()
    normalized_artifact_id = artifact_id.strip()
    if not normalized_group_id or not normalized_artifact_id:
        raise ValueError("group_id and artifact_id are required to build a Maven metadata URL")

    normalized_base_url = base_url.rstrip("/")
    return (
        f"{normalized_base_url}/"
        f"{normalized_group_id.replace('.', '/')}/"
        f"{normalized_artifact_id}/"
        "maven-metadata.xml"
    )


def _is_retryable_fetch_error(exc: Exception) -> bool:
    if isinstance(exc, URLError):
        return True
    if isinstance(exc, HTTPError):
        status_code = getattr(exc, "code", None)
        return status_code not in {400, 401, 403, 404}
    return isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError)


class MavenPomFetcher:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_MAVEN_CENTRAL_BASE_URL,
        http_user_agent: str = "OpenDep-Maven-preprocess/0.1",
        retry_settings: RetrySettings | None = None,
        logger=None,
        opener=None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http_user_agent = http_user_agent
        self._retry_settings = retry_settings or RetrySettings.from_env()
        self._logger = logger or get_logger("preprocess.maven.fetch")
        self._opener = opener or urlopen

    def build_url(self, coordinate: MavenCoordinate | str) -> str:
        return build_pom_url(coordinate, base_url=self._base_url)

    def build_metadata_url(self, coordinate: MavenCoordinate | str) -> str:
        return build_metadata_url(coordinate, base_url=self._base_url)

    def fetch_bytes(self, coordinate: MavenCoordinate | str) -> bytes:
        resolved_coordinate = _normalize_coordinate(coordinate)
        pom_url = self.build_url(resolved_coordinate)
        return self._fetch_url(
            resolved_coordinate.gav,
            pom_url,
            artifact_label="POM",
            not_found_error_cls=PomNotFoundError,
            fetch_error_cls=PomFetchError,
        )

    def fetch_metadata_bytes(self, coordinate: MavenCoordinate | str) -> bytes:
        resolved_coordinate = _normalize_coordinate(coordinate)
        metadata_url = self.build_metadata_url(resolved_coordinate)
        return self._fetch_url(
            resolved_coordinate.ga,
            metadata_url,
            artifact_label="metadata",
            not_found_error_cls=MetadataNotFoundError,
            fetch_error_cls=MetadataFetchError,
        )

    def fetch_package_metadata_bytes(self, group_id: str, artifact_id: str) -> bytes:
        package_key = f"{group_id.strip()}:{artifact_id.strip()}"
        metadata_url = build_package_metadata_url(group_id, artifact_id, base_url=self._base_url)
        return self._fetch_url(
            package_key,
            metadata_url,
            artifact_label="metadata",
            not_found_error_cls=MetadataNotFoundError,
            fetch_error_cls=MetadataFetchError,
        )

    def _fetch_url(
        self,
        request_key: str,
        url: str,
        *,
        artifact_label: str,
        not_found_error_cls,
        fetch_error_cls,
    ) -> bytes:
        def operation() -> bytes:
            request = Request(url, headers={"User-Agent": self._http_user_agent})
            with self._opener(request) as response:
                payload = response.read()
            if not payload:
                raise OSError(f"empty Maven {artifact_label} response for {request_key}")
            return payload

        self._logger.info("Fetching Maven %s for %s from %s", artifact_label, request_key, url)
        try:
            return run_with_retry(
                operation,
                settings=self._retry_settings,
                retry_if=_is_retryable_fetch_error,
                on_retry=lambda attempt, exc, delay: self._logger.warning(
                    "Retrying Maven %s fetch for %s after %s on attempt %s in %.2fs",
                    artifact_label,
                    request_key,
                    exc.__class__.__name__,
                    attempt,
                    delay,
                ),
            )
        except HTTPError as exc:
            if getattr(exc, "code", None) == 404:
                raise not_found_error_cls(f"remote Maven {artifact_label} not found for {request_key} at {url}") from exc
            raise fetch_error_cls(f"failed to fetch Maven {artifact_label} for {request_key} from {url}") from exc
        except (URLError, OSError) as exc:
            raise fetch_error_cls(f"failed to fetch Maven {artifact_label} for {request_key} from {url}") from exc


__all__ = [
    "DEFAULT_MAVEN_CENTRAL_BASE_URL",
    "MetadataFetchError",
    "MetadataNotFoundError",
    "MavenPomFetcher",
    "PomFetchError",
    "PomNotFoundError",
    "build_metadata_url",
    "build_package_metadata_url",
    "build_pom_url",
]
