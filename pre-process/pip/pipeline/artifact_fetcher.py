from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    from packaging.utils import canonicalize_name
except ImportError:  # pragma: no cover
    from pip._vendor.packaging.utils import canonicalize_name


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
COMMON_UTILS_ROOT = PROJECT_ROOT / "pre-process" / "common" / "utils"

for path in (PROJECT_ROOT, COMMON_UTILS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from logging_utils import get_logger
from pip_models import AcquiredArtifact
from resolving.containerization.images.pip.backend.inspectors.selector import (
    ArtifactReference,
    select_preferred_artifacts,
)
from retry import RetrySettings, run_with_retry


def _is_retryable_download_error(exc: Exception) -> bool:
    from urllib.error import HTTPError, URLError

    if isinstance(exc, URLError):
        return True
    if isinstance(exc, HTTPError):
        status_code = getattr(exc, "code", None)
        return status_code not in {400, 401, 403, 404}
    return isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError)


class ArtifactFetcher:
    def __init__(
        self,
        release_source,
        *,
        cache_dir: str | None = None,
        http_user_agent: str = "OpenDep-Pip-preprocess/0.1",
        retry_settings: RetrySettings | None = None,
        logger=None,
    ) -> None:
        self._release_source = release_source
        self._cache_dir = Path(cache_dir).expanduser().resolve() if cache_dir else None
        self._http_user_agent = http_user_agent
        self._retry_settings = retry_settings or RetrySettings.from_env()
        self._logger = logger or get_logger("preprocess.pip.fetch")

    def acquire(
        self,
        project_name: str,
        version: str,
        *,
        mirror_dir: str | None = None,
        cleanup_downloaded_artifacts: bool = False,
    ) -> AcquiredArtifact:
        payload = self._release_source.get_release_payload(project_name, version)
        artifact = self._select_artifact(payload)
        artifact_path, cleanup_artifact_path = self._resolve_artifact_path(
            project_name,
            version,
            artifact,
            mirror_dir=mirror_dir,
            cleanup_downloaded_artifacts=cleanup_downloaded_artifacts,
        )
        return AcquiredArtifact(
            project_name=project_name,
            version=version,
            artifact_path=artifact_path,
            artifact_url=artifact.url,
            artifact_hash=self._artifact_hash(artifact),
            source_kind=artifact.kind,
            cleanup_artifact_path=cleanup_artifact_path,
        )

    def _select_artifact(self, payload: dict[str, object]) -> ArtifactReference:
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

    def _resolve_artifact_path(
        self,
        project_name: str,
        version: str,
        artifact: ArtifactReference,
        *,
        mirror_dir: str | None,
        cleanup_downloaded_artifacts: bool,
    ) -> tuple[str, str | None]:
        cached = self._artifact_cache_path(artifact)
        legacy_cached = self._legacy_artifact_cache_path(artifact)
        for candidate in (cached, legacy_cached):
            if candidate is None or not candidate.exists():
                continue
            self._logger.info("Using cached artifact for %s==%s at %s", project_name, version, candidate)
            cleanup_path = str(candidate) if cleanup_downloaded_artifacts else None
            return str(candidate), cleanup_path

        mirrored = self._resolve_from_mirror(project_name, version, artifact, mirror_dir=mirror_dir)
        if mirrored is not None:
            self._logger.info("Using mirrored artifact for %s==%s at %s", project_name, version, mirrored)
            return str(mirrored), None

        downloaded_path = self._download_artifact(project_name, version, artifact, destination=cached)
        cleanup_path = downloaded_path if cleanup_downloaded_artifacts else None
        return downloaded_path, cleanup_path

    def _resolve_from_mirror(
        self,
        project_name: str,
        version: str,
        artifact: ArtifactReference,
        *,
        mirror_dir: str | None,
    ) -> Path | None:
        if not mirror_dir:
            return None

        mirror_root = Path(mirror_dir).expanduser().resolve()
        if not mirror_root.exists():
            raise FileNotFoundError(f"mirror directory does not exist: {mirror_root}")

        url_path = urlparse(artifact.url or "").path.lstrip("/")
        project_variants = {
            project_name,
            canonicalize_name(project_name),
            project_name.replace("-", "_"),
            canonicalize_name(project_name).replace("-", "_"),
        }
        candidate_paths: list[Path] = []
        if url_path:
            candidate_paths.append(mirror_root / url_path)
            candidate_paths.append(mirror_root / "web" / url_path)

        for variant in sorted(project_variants):
            candidate_paths.append(mirror_root / variant / artifact.filename)
            candidate_paths.append(mirror_root / variant / version / artifact.filename)

        candidate_paths.append(mirror_root / artifact.filename)

        seen: set[Path] = set()
        for candidate in candidate_paths:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if resolved.exists() and resolved.is_file():
                return resolved
        return None

    def _download_artifact(
        self,
        project_name: str,
        version: str,
        artifact: ArtifactReference,
        *,
        destination: Path | None,
    ) -> str:
        if artifact.url is None:
            raise ValueError("artifact url is required for remote download")

        def operation() -> str:
            request = Request(artifact.url, headers={"User-Agent": self._http_user_agent})
            with urlopen(request) as response:
                if destination is None:
                    suffix = "".join(Path(artifact.filename).suffixes) or Path(artifact.filename).suffix
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                        shutil.copyfileobj(response, temp_file)
                        return temp_file.name

                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("wb") as output:
                    shutil.copyfileobj(response, output)
                return str(destination)

        self._logger.info("Downloading artifact for %s==%s from %s", project_name, version, artifact.url)
        return run_with_retry(
            operation,
            settings=self._retry_settings,
            retry_if=_is_retryable_download_error,
            on_retry=lambda attempt, exc, delay: self._logger.warning(
                "Retrying artifact download for %s==%s after %s on attempt %s in %.2fs",
                project_name,
                version,
                exc.__class__.__name__,
                attempt,
                delay,
            ),
        )

    def _artifact_cache_path(self, artifact: ArtifactReference) -> Path | None:
        if self._cache_dir is None:
            return None
        unique = hashlib.sha256((artifact.url or artifact.filename).encode("utf-8")).hexdigest()[:16]
        safe_filename = Path(artifact.filename).name
        return self._cache_dir.joinpath("artifacts", unique, safe_filename)

    def _legacy_artifact_cache_path(self, artifact: ArtifactReference) -> Path | None:
        if self._cache_dir is None:
            return None
        unique = hashlib.sha256((artifact.url or artifact.filename).encode("utf-8")).hexdigest()[:16]
        safe_filename = Path(artifact.filename).name
        return self._cache_dir.joinpath("artifacts", f"{unique}-{safe_filename}")

    def _artifact_hash(self, artifact: ArtifactReference) -> str | None:
        if not artifact.hashes:
            return None
        sha256 = artifact.hashes.get("sha256")
        if sha256:
            return f"sha256:{sha256}"
        for algorithm, digest in artifact.hashes.items():
            return f"{algorithm}:{digest}"
        return None


__all__ = ["ArtifactFetcher"]
