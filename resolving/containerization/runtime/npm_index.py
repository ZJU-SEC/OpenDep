from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import ssl
import sys
import threading
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
COMMON_DATABASE_ROOT = PROJECT_ROOT / "pre-process" / "common" / "database"

for path in (PROJECT_ROOT, COMMON_DATABASE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from postgres import connect_postgres, postgres_cursor


DEFAULT_REGISTRY_BASE_URL = "https://registry.npmmirror.com"
_TABLE_PART_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _normalize_table_name(table_name: str) -> str:
    normalized = table_name.strip()
    if not normalized:
        raise ValueError("npm index table name is required")

    parts = normalized.split(".")
    if not all(_TABLE_PART_PATTERN.fullmatch(part) for part in parts):
        raise ValueError(f"invalid npm index table name `{table_name}`")
    return ".".join(parts)


@dataclass(frozen=True, slots=True)
class IndexedPackument:
    package_name: str
    raw_packument: str


class PostgresPackumentStore:
    def __init__(self, dsn: str, *, table_name: str = "npm_metadata") -> None:
        self._dsn = dsn
        self._table_name = _normalize_table_name(table_name)
        self._connection = None

    @property
    def table_name(self) -> str:
        return self._table_name

    def get_packument(self, package_name: str) -> IndexedPackument | None:
        connection = self._connect()
        with postgres_cursor(connection) as cursor:
            cursor.execute(
                f"SELECT name, raw_packument FROM {self._table_name} WHERE name = %s LIMIT 1",
                (package_name,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return IndexedPackument(package_name=row[0], raw_packument=row[1])

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _connect(self):
        if self._connection is None:
            self._connection = connect_postgres(self._dsn)
        return self._connection


class UpstreamRegistryClient:
    def __init__(self, *, base_url: str, timeout_seconds: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._ssl_context = ssl.create_default_context()

    @property
    def base_url(self) -> str:
        return self._base_url

    def fetch(self, package_name: str) -> tuple[int, bytes, str]:
        package_path = _escape_package_name(package_name)
        url = f"{self._base_url}/{package_path}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "OpenDep-NPM-index-shim/0.1",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds, context=self._ssl_context) as response:
                body = response.read()
                content_type = response.headers.get("Content-Type", "application/json; charset=utf-8")
                return int(response.status), body, content_type
        except HTTPError as exc:
            body = exc.read()
            content_type = exc.headers.get("Content-Type", "application/json; charset=utf-8")
            return int(exc.code), body, content_type
        except URLError as exc:
            raise RuntimeError(f"upstream npm registry request failed: {exc.reason}") from exc


@dataclass(frozen=True, slots=True)
class PackumentShimHandle:
    base_url: str
    server: ThreadingHTTPServer
    thread: threading.Thread
    store: PostgresPackumentStore
    upstream_client: UpstreamRegistryClient | None


def _escape_package_name(package_name: str) -> str:
    from urllib.parse import quote

    normalized = package_name.strip()
    if not normalized:
        raise ValueError("package name is required")
    return quote(normalized, safe="@")


def _package_name_from_request_path(raw_path: str) -> str:
    parsed = urlsplit(raw_path)
    stripped_path = parsed.path.lstrip("/")
    package_name = unquote(stripped_path).strip()
    if not package_name:
        raise ValueError("package name is required")
    return package_name


def _json_error_body(message: str) -> bytes:
    return json.dumps({"error": "not_found", "reason": message}, ensure_ascii=False).encode("utf-8")


@contextmanager
def serve_packument_shim(
    *,
    dsn: str,
    table_name: str,
    upstream_base_url: str | None,
    fallback_to_online: bool,
) -> Iterator[PackumentShimHandle]:
    store = PostgresPackumentStore(dsn, table_name=table_name)
    upstream_client = None
    if fallback_to_online and upstream_base_url:
        upstream_client = UpstreamRegistryClient(base_url=upstream_base_url)

    class PackumentShimHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            try:
                package_name = _package_name_from_request_path(self.path)
            except ValueError as exc:
                self._write_response(400, _json_error_body(str(exc)))
                return

            try:
                indexed_packument = store.get_packument(package_name)
            except Exception as exc:
                self._write_response(502, _json_error_body(f"index lookup failed: {exc}"))
                return

            if indexed_packument is not None:
                self._write_response(
                    200,
                    indexed_packument.raw_packument.encode("utf-8"),
                    source="indexed-postgres",
                )
                return

            if upstream_client is None:
                self._write_response(
                    404,
                    _json_error_body(f"packument not found for `{package_name}`"),
                    source="indexed-postgres",
                )
                return

            try:
                status_code, response_body, content_type = upstream_client.fetch(package_name)
            except Exception as exc:
                self._write_response(502, _json_error_body(str(exc)), source="fallback-online")
                return

            self._write_response(
                status_code,
                response_body,
                content_type=content_type,
                source="fallback-online",
            )

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return None

        def _write_response(
            self,
            status_code: int,
            body: bytes,
            *,
            content_type: str = "application/json; charset=utf-8",
            source: str | None = None,
        ) -> None:
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if source:
                self.send_header("X-OpenDep-Packument-Source", source)
            self.end_headers()
            self.wfile.write(body)

    class ReusableThreadingHTTPServer(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    server = ReusableThreadingHTTPServer(("127.0.0.1", 0), PackumentShimHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        yield PackumentShimHandle(
            base_url=f"http://{host}:{port}",
            server=server,
            thread=thread,
            store=store,
            upstream_client=upstream_client,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        store.close()
