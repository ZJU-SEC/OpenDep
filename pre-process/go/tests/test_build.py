from __future__ import annotations

import io
import json
import threading
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from unittest.mock import patch

from support import PROJECT_ROOT

import build as go_build


class FakeLoader:
    existing_modules: set[tuple[str, str]] = set()
    instances: list["FakeLoader"] = []

    def __init__(self, *, dsn=None, table_name=None, schema_file=None, connection=None) -> None:
        self.dsn = dsn
        self.table_name = table_name or "go_metadata"
        self.schema_file = schema_file
        self.connection = connection
        self.ensure_schema_called = False
        self.closed = False
        self.upserted_records = []
        FakeLoader.instances.append(self)

    def ensure_schema(self) -> None:
        self.ensure_schema_called = True

    def table_exists(self) -> bool:
        return True

    def has_module(self, module_path: str, version: str) -> bool:
        return (module_path, version) in self.existing_modules

    def upsert_record(self, record) -> None:
        self.upserted_records.append(record)

    def close(self) -> None:
        self.closed = True


class FakeProxyClient:
    delays: dict[tuple[str, str], float] = {}
    listed_versions: dict[str, tuple[str, ...]] = {}
    instances: list["FakeProxyClient"] = []
    current_calls = 0
    max_parallel = 0
    lock = threading.Lock()

    def __init__(self, *, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.fetch_calls: list[tuple[str, str]] = []
        self.list_calls: list[str] = []
        FakeProxyClient.instances.append(self)

    def list_versions(self, module_path: str) -> tuple[str, ...]:
        self.list_calls.append(module_path)
        return self.listed_versions.get(module_path, ())

    def fetch_raw_mod(self, module_path: str, version: str):
        self.fetch_calls.append((module_path, version))
        with self.lock:
            FakeProxyClient.current_calls += 1
            FakeProxyClient.max_parallel = max(FakeProxyClient.max_parallel, FakeProxyClient.current_calls)
        try:
            time.sleep(self.delays.get((module_path, version), 0.0))
            return type(
                "Download",
                (),
                {
                    "module_path": module_path,
                    "version": version,
                    "raw_mod": f"module {module_path}\n",
                    "source_url": f"{self.base_url}/{module_path}/@v/{version}.mod",
                    "fetched_at": datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
                },
            )()
        finally:
            with self.lock:
                FakeProxyClient.current_calls -= 1


class BuildCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeLoader.existing_modules = set()
        FakeLoader.instances = []
        FakeProxyClient.delays = {}
        FakeProxyClient.listed_versions = {}
        FakeProxyClient.instances = []
        FakeProxyClient.current_calls = 0
        FakeProxyClient.max_parallel = 0

    def test_skip_existing_avoids_proxy_fetch_and_reports_counts(self) -> None:
        FakeLoader.existing_modules = {("example.com/already", "v1.0.0")}
        stdout = io.StringIO()

        with patch.object(go_build, "GoModuleModfilePostgresLoader", FakeLoader), patch.object(
            go_build, "GoProxyClient", FakeProxyClient
        ), redirect_stdout(stdout):
            exit_code = go_build.main(
                [
                    "--module",
                    "example.com/already@v1.0.0",
                    "--module",
                    "example.com/new@v1.1.0",
                    "--skip-existing",
                ]
            )

        payload = json.loads(stdout.getvalue())
        loader = FakeLoader.instances[0]
        client = FakeProxyClient.instances[0]

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["skipped_count"], 1)
        self.assertEqual(payload["summary"]["stored_count"], 1)
        self.assertEqual(payload["results"][0]["status"], "skipped")
        self.assertEqual(payload["results"][1]["status"], "stored")
        self.assertEqual(client.fetch_calls, [("example.com/new", "v1.1.0")])
        self.assertEqual(len(loader.upserted_records), 1)
        self.assertTrue(loader.closed)

    def test_unversioned_module_expands_to_all_listed_versions(self) -> None:
        FakeProxyClient.listed_versions = {
            "example.com/library": ("v1.0.0", "v1.1.0"),
        }
        stdout = io.StringIO()

        with patch.object(go_build, "GoModuleModfilePostgresLoader", FakeLoader), patch.object(
            go_build, "GoProxyClient", FakeProxyClient
        ), redirect_stdout(stdout):
            exit_code = go_build.main(
                [
                    "--module",
                    "example.com/library",
                ]
            )

        payload = json.loads(stdout.getvalue())
        client = FakeProxyClient.instances[0]

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["input_count"], 1)
        self.assertEqual(payload["requested_count"], 2)
        self.assertEqual(payload["summary"]["stored_count"], 2)
        self.assertEqual(client.list_calls, ["example.com/library"])
        self.assertEqual(
            client.fetch_calls,
            [("example.com/library", "v1.0.0"), ("example.com/library", "v1.1.0")],
        )
        self.assertEqual(
            [item["version"] for item in payload["results"]],
            ["v1.0.0", "v1.1.0"],
        )

    def test_concurrency_allows_parallel_fetches(self) -> None:
        FakeProxyClient.delays = {
            ("example.com/a", "v1.0.0"): 0.05,
            ("example.com/b", "v1.0.0"): 0.05,
            ("example.com/c", "v1.0.0"): 0.05,
        }
        stdout = io.StringIO()

        with patch.object(go_build, "GoModuleModfilePostgresLoader", FakeLoader), patch.object(
            go_build, "GoProxyClient", FakeProxyClient
        ), redirect_stdout(stdout):
            exit_code = go_build.main(
                [
                    "--module",
                    "example.com/a@v1.0.0",
                    "--module",
                    "example.com/b@v1.0.0",
                    "--module",
                    "example.com/c@v1.0.0",
                    "--concurrency",
                    "3",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["source"]["concurrency"], 3)
        self.assertEqual(payload["summary"]["stored_count"], 3)
        self.assertGreaterEqual(FakeProxyClient.max_parallel, 2)


if __name__ == "__main__":
    unittest.main()
