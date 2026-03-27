from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Callable
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
from pip_models import VersionPlanItem
from retry import RetrySettings, run_with_retry


JsonFetcher = Callable[[str], dict[str, Any]]


def _is_retryable_fetch_error(exc: Exception) -> bool:
    from urllib.error import HTTPError, URLError

    if isinstance(exc, URLError):
        return True
    if isinstance(exc, HTTPError):
        status_code = getattr(exc, "code", None)
        return status_code not in {400, 401, 403, 404}
    return isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError)


def _normalize_base_url(base_url: str) -> str:
    if "://" not in base_url:
        candidate = Path(base_url).expanduser()
        if candidate.exists():
            return candidate.resolve().as_uri().rstrip("/")
    return base_url.rstrip("/")


class PyPIJsonClient:
    def __init__(
        self,
        *,
        cache_dir: str | None = None,
        pypi_json_base_url: str = "https://pypi.org/pypi",
        http_user_agent: str = "OpenDep-Pip-preprocess/0.1",
        json_fetcher: JsonFetcher | None = None,
        retry_settings: RetrySettings | None = None,
        logger=None,
    ) -> None:
        self._cache_dir = Path(cache_dir).expanduser().resolve() if cache_dir else None
        self._pypi_json_base_url = _normalize_base_url(pypi_json_base_url)
        self._http_user_agent = http_user_agent
        self._json_fetcher = json_fetcher or self._fetch_json
        self._retry_settings = retry_settings or RetrySettings.from_env()
        self._logger = logger or get_logger("preprocess.pip.pypi")

    def list_versions(self, project_name: str) -> list[VersionPlanItem]:
        normalized_name = canonicalize_name(project_name)
        cached = self._load_cached_project_payload(normalized_name)
        payload = cached if cached is not None else self._fetch_project_payload(normalized_name)
        if cached is None:
            self._store_project_payload(normalized_name, payload)
        return self._extract_versions(normalized_name, payload)

    def get_release_payload(self, project_name: str, version: str) -> dict[str, Any]:
        normalized_name = canonicalize_name(project_name)
        cached = self._load_cached_release_payload(normalized_name, version)
        if cached is not None:
            return cached
        payload = self._fetch_release_payload(normalized_name, version)
        self._store_release_payload(normalized_name, version, payload)
        return payload

    def _fetch_project_payload(self, project_name: str) -> dict[str, Any]:
        url = f"{self._pypi_json_base_url}/{project_name}/json"
        self._logger.info("Fetching project JSON for %s", project_name)
        return run_with_retry(
            lambda: self._json_fetcher(url),
            settings=self._retry_settings,
            retry_if=_is_retryable_fetch_error,
            on_retry=lambda attempt, exc, delay: self._logger.warning(
                "Retrying project JSON fetch for %s after %s on attempt %s in %.2fs",
                project_name,
                exc.__class__.__name__,
                attempt,
                delay,
            ),
        )

    def _fetch_release_payload(self, project_name: str, version: str) -> dict[str, Any]:
        url = f"{self._pypi_json_base_url}/{project_name}/{version}/json"
        self._logger.info("Fetching release JSON for %s==%s", project_name, version)
        return run_with_retry(
            lambda: self._json_fetcher(url),
            settings=self._retry_settings,
            retry_if=_is_retryable_fetch_error,
            on_retry=lambda attempt, exc, delay: self._logger.warning(
                "Retrying release JSON fetch for %s==%s after %s on attempt %s in %.2fs",
                project_name,
                version,
                exc.__class__.__name__,
                attempt,
                delay,
            ),
        )

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

    def _cache_path(self, *parts: str) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir.joinpath("pypi-json", *parts)

    def _load_cached_project_payload(self, project_name: str) -> dict[str, Any] | None:
        path = self._cache_path("projects", f"{project_name}.json")
        if path is None or not path.exists():
            return None
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else None

    def _store_project_payload(self, project_name: str, payload: dict[str, Any]) -> None:
        path = self._cache_path("projects", f"{project_name}.json")
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_cached_release_payload(self, project_name: str, version: str) -> dict[str, Any] | None:
        path = self._cache_path("releases", project_name, f"{version}.json")
        if path is None or not path.exists():
            return None
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else None

    def _store_release_payload(self, project_name: str, version: str, payload: dict[str, Any]) -> None:
        path = self._cache_path("releases", project_name, f"{version}.json")
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _extract_versions(self, project_name: str, payload: dict[str, Any]) -> list[VersionPlanItem]:
        releases = payload.get("releases", {})
        records: list[VersionPlanItem] = []
        if isinstance(releases, dict):
            for version, files in releases.items():
                yanked = False
                if isinstance(files, list) and files:
                    yanked = all(bool(entry.get("yanked", False)) for entry in files if isinstance(entry, dict))
                records.append(
                    VersionPlanItem(
                        project_name=payload.get("info", {}).get("name") or project_name,
                        version=str(version),
                        yanked=yanked,
                        source_kind="live-index",
                    )
                )
        return self._sort_versions(records)

    def _sort_versions(self, versions: list[VersionPlanItem]) -> list[VersionPlanItem]:
        try:
            from packaging.version import InvalidVersion, Version
        except ImportError:  # pragma: no cover
            from pip._vendor.packaging.version import InvalidVersion, Version

        def sort_key(record: VersionPlanItem):
            try:
                return (1, Version(record.version))
            except InvalidVersion:
                return (0, record.version)

        return sorted(versions, key=sort_key, reverse=True)


__all__ = ["PyPIJsonClient"]
