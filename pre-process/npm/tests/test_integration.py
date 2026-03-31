from __future__ import annotations

from contextlib import closing, redirect_stdout
import io
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from support import COMMON_DATABASE_ROOT, PROJECT_ROOT

import build as npm_build
from adapters.registry_client import escape_package_name
from postgres import connect_postgres, postgres_cursor, postgres_transaction, resolve_dsn


class StubRegistryHandler(BaseHTTPRequestHandler):
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
        self.send_header("Content-Type", "application/json; charset=utf-8")
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
class NpmBuildIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._schema_file_path: Path | None = None
        self._http_server: ThreadingHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._table_name = f"npm_metadata_it_{uuid4().hex[:8]}"

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

    def test_build_stores_and_queries_raw_packument_by_package_name(self) -> None:
        package_name = "@types/node"
        raw_packument = json.dumps(
            {
                "_id": package_name,
                "_rev": "42-abcdef",
                "dist-tags": {"latest": "24.0.0"},
                "versions": {
                    "24.0.0": {
                        "dependencies": {"undici-types": "~7.10.0"},
                    }
                },
            },
            ensure_ascii=False,
        )
        route = f"/{escape_package_name(package_name)}"
        base_url = self._start_stub_registry({route: raw_packument})
        schema_file = self._write_schema_file()
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = npm_build.main(
                [
                    "--package",
                    package_name,
                    "--dsn",
                    resolve_dsn(),
                    "--table",
                    self._table_name,
                    "--schema-file",
                    str(schema_file),
                    "--ensure-schema",
                    "--registry-base-url",
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
                        f"SELECT name, raw_packument, source_url, source_rev FROM {self._table_name} "
                        "WHERE name = %s"
                    ),
                    (package_name,),
                )
                row = cursor.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], package_name)
        self.assertEqual(row[1], raw_packument)
        self.assertEqual(row[2], f"{base_url}/{escape_package_name(package_name)}")
        self.assertEqual(row[3], "42-abcdef")

    def _write_schema_file(self) -> Path:
        template = (COMMON_DATABASE_ROOT / "initdb" / "20-npm-metadata.sql").read_text(encoding="utf-8")
        rewritten = (
            template.replace("public.npm_metadata", f"public.{self._table_name}")
            .replace("uq_npm_metadata_name", f"uq_{self._table_name}_name")
            .replace("idx_npm_metadata_updated_at", f"idx_{self._table_name}_updated_at")
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

    def _start_stub_registry(self, routes: dict[str, str]) -> str:
        StubRegistryHandler.routes = routes
        server = ThreadingHTTPServer(("127.0.0.1", 0), StubRegistryHandler)
        self._http_server = server
        self._server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._server_thread.start()
        host, port = server.server_address
        return f"http://{host}:{port}"


if __name__ == "__main__":
    unittest.main()
