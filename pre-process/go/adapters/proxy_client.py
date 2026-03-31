from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None


DEFAULT_PROXY_BASE_URL = "https://proxy.golang.org"


class GoProxyClientError(RuntimeError):
    def __init__(self, message: str, *, url: str, status_code: int | None = None, detail: str | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class GoModDownload:
    module_path: str
    version: str
    raw_mod: str
    source_url: str
    fetched_at: datetime


def _escape_proxy_token(value: str, *, label: str, allow_bang: bool) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    if any(ord(char) >= 128 for char in normalized):
        raise ValueError(f"{label} must be ASCII to match Go proxy escaping rules")
    if not allow_bang and "!" in normalized:
        raise ValueError(f"{label} cannot contain `!`")

    escaped: list[str] = []
    for char in normalized:
        if "A" <= char <= "Z":
            escaped.extend(("!", char.lower()))
        else:
            escaped.append(char)
    return "".join(escaped)


def escape_module_path(module_path: str) -> str:
    return _escape_proxy_token(module_path, label="module path", allow_bang=False)


def escape_module_version(version: str) -> str:
    return _escape_proxy_token(version, label="module version", allow_bang=False)


class GoProxyClient:
    def __init__(self, *, base_url: str = DEFAULT_PROXY_BASE_URL, timeout_seconds: float = 120.0) -> None:
        self._base_url = (base_url or DEFAULT_PROXY_BASE_URL).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._ssl_context = _build_ssl_context()

    @property
    def base_url(self) -> str:
        return self._base_url

    def build_mod_url(self, module_path: str, version: str) -> str:
        escaped_path = escape_module_path(module_path)
        escaped_version = escape_module_version(version)
        return f"{self._base_url}/{escaped_path}/@v/{escaped_version}.mod"

    def build_list_url(self, module_path: str) -> str:
        escaped_path = escape_module_path(module_path)
        return f"{self._base_url}/{escaped_path}/@v/list"

    def list_versions(self, module_path: str) -> tuple[str, ...]:
        request_url = self.build_list_url(module_path)
        request = Request(
            request_url,
            headers={"User-Agent": "opendep-go-preprocess/0.1"},
            method="GET",
        )

        try:
            with urlopen(request, timeout=self._timeout_seconds, context=self._ssl_context) as response:
                body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip() or None
            raise GoProxyClientError(
                f"go proxy returned status {exc.code} while listing versions for {module_path}",
                url=request_url,
                status_code=exc.code,
                detail=detail,
            ) from exc
        except URLError as exc:
            raise GoProxyClientError(
                f"go proxy version listing failed for {module_path}: {exc.reason}",
                url=request_url,
            ) from exc

        ordered_versions: dict[str, None] = {}
        for line in body.splitlines():
            version = line.strip()
            if version:
                ordered_versions[version] = None
        return tuple(ordered_versions)

    def fetch_raw_mod(self, module_path: str, version: str) -> GoModDownload:
        request_url = self.build_mod_url(module_path, version)
        request = Request(
            request_url,
            headers={"User-Agent": "opendep-go-preprocess/0.1"},
            method="GET",
        )

        try:
            with urlopen(request, timeout=self._timeout_seconds, context=self._ssl_context) as response:
                body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip() or None
            raise GoProxyClientError(
                f"go proxy returned status {exc.code} for {module_path}@{version}",
                url=request_url,
                status_code=exc.code,
                detail=detail,
            ) from exc
        except URLError as exc:
            raise GoProxyClientError(
                f"go proxy request failed for {module_path}@{version}: {exc.reason}",
                url=request_url,
            ) from exc

        return GoModDownload(
            module_path=module_path,
            version=version,
            raw_mod=body,
            source_url=request_url,
            fetched_at=datetime.now(timezone.utc),
        )


def _build_ssl_context() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()
