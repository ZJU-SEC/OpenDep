from __future__ import annotations

from dataclasses import dataclass
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None


DEFAULT_CHANGES_URL = "https://replicate.npmjs.com/registry/_changes"
DEFAULT_SYNC_REGISTRY_BASE_URL = "https://replicate.npmjs.com/registry"


class NpmChangesClientError(RuntimeError):
    def __init__(self, message: str, *, url: str, status_code: int | None = None, detail: str | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class NpmChangeEvent:
    package_name: str
    sequence: str | None
    changes_rev: str | None
    deleted: bool = False


@dataclass(frozen=True, slots=True)
class NpmChangesBatch:
    events: list[NpmChangeEvent]
    last_seq: str | None
    source_url: str


class NpmChangesClient:
    def __init__(self, *, changes_url: str = DEFAULT_CHANGES_URL, timeout_seconds: float = 120.0) -> None:
        self._changes_url = (changes_url or DEFAULT_CHANGES_URL).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._ssl_context = _build_ssl_context()

    @property
    def changes_url(self) -> str:
        return self._changes_url

    def build_changes_request_url(self, *, since: str | None = None, limit: int = 1000) -> str:
        params: dict[str, str] = {"limit": str(limit)}
        if since is not None and str(since).strip():
            params["last-event-id"] = str(since)
        return f"{self._changes_url}?{urlencode(params)}"

    def fetch_changes_batch(self, *, since: str | None = None, limit: int = 1000) -> NpmChangesBatch:
        request_url = self.build_changes_request_url(since=since, limit=limit)
        request = Request(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "OpenDep-NPM-sync/0.1",
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=self._timeout_seconds, context=self._ssl_context) as response:
                body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip() or None
            raise NpmChangesClientError(
                f"npm changes feed returned status {exc.code}",
                url=request_url,
                status_code=exc.code,
                detail=detail,
            ) from exc
        except URLError as exc:
            raise NpmChangesClientError(
                f"npm changes feed request failed: {exc.reason}",
                url=request_url,
            ) from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise NpmChangesClientError(
                "npm changes feed returned invalid JSON",
                url=request_url,
                detail=str(exc),
            ) from exc

        if not isinstance(payload, dict):
            raise NpmChangesClientError(
                "npm changes feed returned a non-object payload",
                url=request_url,
            )

        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raise NpmChangesClientError(
                "npm changes feed payload is missing `results`",
                url=request_url,
            )

        events: list[NpmChangeEvent] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            package_name = item.get("id")
            if not isinstance(package_name, str) or not package_name.strip():
                continue

            raw_changes = item.get("changes")
            changes_rev: str | None = None
            if isinstance(raw_changes, list) and raw_changes:
                last_change = raw_changes[-1]
                if isinstance(last_change, dict):
                    raw_rev = last_change.get("rev")
                    if isinstance(raw_rev, str) and raw_rev.strip():
                        changes_rev = raw_rev

            raw_seq = item.get("seq")
            sequence = str(raw_seq) if raw_seq is not None else None
            deleted = bool(item.get("deleted"))
            events.append(
                NpmChangeEvent(
                    package_name=package_name,
                    sequence=sequence,
                    changes_rev=changes_rev,
                    deleted=deleted,
                )
            )

        raw_last_seq = payload.get("last_seq")
        last_seq = str(raw_last_seq) if raw_last_seq is not None else None
        return NpmChangesBatch(events=events, last_seq=last_seq, source_url=request_url)


def _build_ssl_context() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()
