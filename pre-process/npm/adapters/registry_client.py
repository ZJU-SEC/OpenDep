from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None


DEFAULT_REGISTRY_BASE_URL = "https://registry.npmjs.org"


class NpmRegistryClientError(RuntimeError):
    def __init__(self, message: str, *, url: str, status_code: int | None = None, detail: str | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class NpmPackumentDownload:
    name: str
    raw_packument: str
    source_url: str
    fetched_at: datetime
    source_rev: str | None = None


def escape_package_name(package_name: str) -> str:
    normalized = package_name.strip()
    if not normalized:
        raise ValueError("package name is required")
    return quote(normalized, safe="@")


class NpmRegistryClient:
    def __init__(self, *, base_url: str = DEFAULT_REGISTRY_BASE_URL, timeout_seconds: float = 120.0) -> None:
        self._base_url = (base_url or DEFAULT_REGISTRY_BASE_URL).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._ssl_context = _build_ssl_context()

    @property
    def base_url(self) -> str:
        return self._base_url

    def build_packument_url(self, package_name: str) -> str:
        return f"{self._base_url}/{escape_package_name(package_name)}"

    def fetch_raw_packument(self, package_name: str) -> NpmPackumentDownload:
        request_url = self.build_packument_url(package_name)
        request = Request(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "OpenDep-NPM-preprocess/0.1",
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=self._timeout_seconds, context=self._ssl_context) as response:
                body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip() or None
            raise NpmRegistryClientError(
                f"npm registry returned status {exc.code} for {package_name}",
                url=request_url,
                status_code=exc.code,
                detail=detail,
            ) from exc
        except URLError as exc:
            raise NpmRegistryClientError(
                f"npm registry request failed for {package_name}: {exc.reason}",
                url=request_url,
            ) from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise NpmRegistryClientError(
                f"npm registry returned invalid JSON for {package_name}",
                url=request_url,
                detail=str(exc),
            ) from exc

        if not isinstance(payload, dict):
            raise NpmRegistryClientError(
                f"npm registry returned a non-object packument for {package_name}",
                url=request_url,
            )

        resolved_name = payload.get("_id") if isinstance(payload.get("_id"), str) and payload.get("_id") else package_name
        source_rev = payload.get("_rev") if isinstance(payload.get("_rev"), str) and payload.get("_rev") else None
        return NpmPackumentDownload(
            name=resolved_name,
            raw_packument=body,
            source_url=request_url,
            fetched_at=datetime.now(timezone.utc),
            source_rev=source_rev,
        )


def _build_ssl_context() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()
