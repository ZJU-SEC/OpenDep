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

import build as npm_build


class FakeLoader:
    existing_packages: set[str] = set()
    instances: list["FakeLoader"] = []

    def __init__(self, *, dsn=None, table_name=None, schema_file=None, connection=None) -> None:
        self.dsn = dsn
        self.table_name = table_name or "npm_metadata"
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

    def has_package(self, package_name: str) -> bool:
        return package_name in self.existing_packages

    def upsert_record(self, record) -> None:
        self.upserted_records.append(record)

    def close(self) -> None:
        self.closed = True


class FakeRegistryClient:
    delays: dict[str, float] = {}
    instances: list["FakeRegistryClient"] = []
    current_calls = 0
    max_parallel = 0
    lock = threading.Lock()

    def __init__(self, *, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.fetch_calls: list[str] = []
        FakeRegistryClient.instances.append(self)

    def fetch_raw_packument(self, package_name: str):
        self.fetch_calls.append(package_name)
        with self.lock:
            FakeRegistryClient.current_calls += 1
            FakeRegistryClient.max_parallel = max(FakeRegistryClient.max_parallel, FakeRegistryClient.current_calls)
        try:
            time.sleep(self.delays.get(package_name, 0.0))
            return type(
                "Download",
                (),
                {
                    "name": package_name,
                    "raw_packument": json.dumps({"_id": package_name, "versions": {}}, ensure_ascii=False),
                    "source_url": f"{self.base_url}/{package_name}",
                    "source_rev": "1-abc",
                    "fetched_at": datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
                },
            )()
        finally:
            with self.lock:
                FakeRegistryClient.current_calls -= 1


class BuildCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeLoader.existing_packages = set()
        FakeLoader.instances = []
        FakeRegistryClient.delays = {}
        FakeRegistryClient.instances = []
        FakeRegistryClient.current_calls = 0
        FakeRegistryClient.max_parallel = 0

    def test_skip_existing_avoids_registry_fetch_and_reports_counts(self) -> None:
        FakeLoader.existing_packages = {"is-odd"}
        stdout = io.StringIO()

        with patch.object(npm_build, "NpmPackumentPostgresLoader", FakeLoader), patch.object(
            npm_build, "NpmRegistryClient", FakeRegistryClient
        ), redirect_stdout(stdout):
            exit_code = npm_build.main(
                [
                    "--package",
                    "is-odd",
                    "--package",
                    "@types/node",
                    "--skip-existing",
                ]
            )

        payload = json.loads(stdout.getvalue())
        loader = FakeLoader.instances[0]
        client = FakeRegistryClient.instances[0]

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["skipped_count"], 1)
        self.assertEqual(payload["summary"]["stored_count"], 1)
        self.assertEqual(payload["results"][0]["status"], "skipped")
        self.assertEqual(payload["results"][1]["status"], "stored")
        self.assertEqual(client.fetch_calls, ["@types/node"])
        self.assertEqual(len(loader.upserted_records), 1)
        self.assertTrue(loader.closed)

    def test_duplicate_inputs_are_deduplicated_before_fetch(self) -> None:
        stdout = io.StringIO()

        with patch.object(npm_build, "NpmPackumentPostgresLoader", FakeLoader), patch.object(
            npm_build, "NpmRegistryClient", FakeRegistryClient
        ), redirect_stdout(stdout):
            exit_code = npm_build.main(
                [
                    "--package",
                    "is-odd",
                    "--package",
                    "is-odd",
                    "--package",
                    "@types/node",
                ]
            )

        payload = json.loads(stdout.getvalue())
        client = FakeRegistryClient.instances[0]

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["input_count"], 2)
        self.assertEqual(payload["requested_count"], 2)
        self.assertEqual(payload["summary"]["stored_count"], 2)
        self.assertEqual(client.fetch_calls, ["is-odd", "@types/node"])

    def test_concurrency_allows_parallel_fetches(self) -> None:
        FakeRegistryClient.delays = {
            "is-odd": 0.05,
            "@types/node": 0.05,
            "left-pad": 0.05,
        }
        stdout = io.StringIO()

        with patch.object(npm_build, "NpmPackumentPostgresLoader", FakeLoader), patch.object(
            npm_build, "NpmRegistryClient", FakeRegistryClient
        ), redirect_stdout(stdout):
            exit_code = npm_build.main(
                [
                    "--package",
                    "is-odd",
                    "--package",
                    "@types/node",
                    "--package",
                    "left-pad",
                    "--concurrency",
                    "3",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["source"]["concurrency"], 3)
        self.assertEqual(payload["summary"]["stored_count"], 3)
        self.assertGreaterEqual(FakeRegistryClient.max_parallel, 2)


if __name__ == "__main__":
    unittest.main()
