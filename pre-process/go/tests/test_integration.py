from __future__ import annotations

from contextlib import closing
import io
import json
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from support import COMMON_DATABASE_ROOT, PROJECT_ROOT

import build as go_build
from adapters.proxy_client import escape_module_path, escape_module_version
from postgres import connect_postgres, postgres_cursor, postgres_transaction, resolve_dsn


class StubProxyHandler(BaseHTTPRequestHandler):
    routes: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802
        body = self.routes.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")
            return

        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return None


def _is_postgres_available() -> bool:
    try:
        with closing(connect_postgres(resolve_dsn())) as connection:
            with postgres_cursor(connection) as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return True
    except Exception:
        return False


@unittest.skipUnless(_is_postgres_available(), "local PostgreSQL is not available")
class GoBuildIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._schema_file_path: Path | None = None
        self._http_server: ThreadingHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._table_name = f"go_metadata_it_{uuid4().hex[:8]}"

    def tearDown(self) -> None:
        if self._http_server is not None:
            self._http_server.shutdown()
            self._http_server.server_close()
        if self._server_thread is not None:
            self._server_thread.join(timeout=5)
        if self._schema_file_path is not None and self._schema_file_path.exists():
            self._schema_file_path.unlink()

        with closing(connect_postgres(resolve_dsn())) as connection:
            with postgres_transaction(connection):
                with postgres_cursor(connection) as cursor:
                    cursor.execute(f"DROP TABLE IF EXISTS {self._table_name}")

    def test_build_stores_and_queries_raw_mod_by_module_and_version(self) -> None:
        module_path = "GitHub.com/Google/UUID"
        version = "V1.2.3-RC1"
        raw_mod = "module GitHub.com/Google/UUID\n\ngo 1.23\n"
        escaped_path = escape_module_path(module_path)
        escaped_version = escape_module_version(version)
        route = f"/{escaped_path}/@v/{escaped_version}.mod"
        base_url = self._start_stub_proxy({route: raw_mod})
        schema_file = self._write_schema_file()
        stdout = io.StringIO()

        from contextlib import redirect_stdout

        with redirect_stdout(stdout):
            exit_code = go_build.main(
                [
                    "--module",
                    f"{module_path}@{version}",
                    "--dsn",
                    resolve_dsn(),
                    "--table",
                    self._table_name,
                    "--schema-file",
                    str(schema_file),
                    "--ensure-schema",
                    "--proxy-base-url",
                    base_url,
                    "--pretty",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["stored_count"], 1)

        with closing(connect_postgres(resolve_dsn())) as connection:
            with postgres_cursor(connection) as cursor:
                cursor.execute(
                    (
                        f"SELECT raw_mod, source_url FROM {self._table_name} "
                        "WHERE module_path = %s AND version = %s"
                    ),
                    (module_path, version),
                )
                row = cursor.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], raw_mod)
        self.assertEqual(row[1], f"{base_url}/{escaped_path}/@v/{escaped_version}.mod")

    def test_build_without_explicit_version_lists_and_stores_all_versions(self) -> None:
        module_path = "example.com/library"
        versions = ("v1.0.0", "v1.1.0")
        routes = {
            f"/{escape_module_path(module_path)}/@v/list": "\n".join(versions) + "\n",
        }
        for version in versions:
            routes[f"/{escape_module_path(module_path)}/@v/{escape_module_version(version)}.mod"] = (
                f"module {module_path}\n"
            )

        base_url = self._start_stub_proxy(routes)
        schema_file = self._write_schema_file()
        stdout = io.StringIO()

        from contextlib import redirect_stdout

        with redirect_stdout(stdout):
            exit_code = go_build.main(
                [
                    "--module",
                    module_path,
                    "--dsn",
                    resolve_dsn(),
                    "--table",
                    self._table_name,
                    "--schema-file",
                    str(schema_file),
                    "--ensure-schema",
                    "--proxy-base-url",
                    base_url,
                    "--pretty",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["input_count"], 1)
        self.assertEqual(payload["requested_count"], 2)
        self.assertEqual(payload["summary"]["stored_count"], 2)

        with closing(connect_postgres(resolve_dsn())) as connection:
            with postgres_cursor(connection) as cursor:
                cursor.execute(
                    (
                        f"SELECT module_path, version FROM {self._table_name} "
                        "WHERE module_path = %s ORDER BY version"
                    ),
                    (module_path,),
                )
                rows = cursor.fetchall()

        self.assertEqual(rows, [(module_path, "v1.0.0"), (module_path, "v1.1.0")])

    def _write_schema_file(self) -> Path:
        template = (COMMON_DATABASE_ROOT / "initdb" / "10-go-metadata.sql").read_text(encoding="utf-8")
        table_index_name = f"idx_{self._table_name}_updated_at"
        rewritten = template.replace("public.go_metadata", f"public.{self._table_name}").replace(
            "idx_go_metadata_updated_at", table_index_name
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".sql",
            prefix=f"{self._table_name}_",
            dir=PROJECT_ROOT,
            delete=False,
        ) as handle:
            handle.write(rewritten)
            self._schema_file_path = Path(handle.name)
        return self._schema_file_path

    def _start_stub_proxy(self, routes: dict[str, str]) -> str:
        StubProxyHandler.routes = routes
        server = ThreadingHTTPServer(("127.0.0.1", 0), StubProxyHandler)
        self._http_server = server
        self._server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._server_thread.start()
        host, port = server.server_address
        return f"http://{host}:{port}"


if __name__ == "__main__":
    unittest.main()
