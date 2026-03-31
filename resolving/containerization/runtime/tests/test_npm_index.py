from __future__ import annotations

from contextlib import closing
import json
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from support import PROJECT_ROOT

from resolving.containerization.runtime import npm_index


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self._connection = connection
        self._fetchone_result = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, query: str, params=None) -> None:
        self._connection.executed.append((query, params))
        package_name = params[0] if params else None
        self._fetchone_result = self._connection.rows.get(package_name)

    def fetchone(self):
        return self._fetchone_result


class FakeConnection:
    def __init__(self, rows: dict[str, tuple[str, str] | None]) -> None:
        self.rows = rows
        self.executed: list[tuple[str, tuple[object, ...] | None]] = []
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def close(self) -> None:
        self.closed = True


class FakeUpstreamRegistryClient:
    def __init__(self, *, base_url: str, timeout_seconds: float = 120.0) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def fetch(self, package_name: str) -> tuple[int, bytes, str]:
        body = json.dumps({"_id": package_name, "versions": {"1.0.0": {}}}, ensure_ascii=False).encode("utf-8")
        return 200, body, "application/json; charset=utf-8"


class NpmIndexTests(unittest.TestCase):
    def test_invalid_table_name_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid npm index table name"):
            npm_index.PostgresPackumentStore("postgresql://example", table_name="npm metadata")

    def test_packument_shim_serves_indexed_packument(self) -> None:
        connection = FakeConnection(
            rows={
                "@types/node": (
                    "@types/node",
                    json.dumps({"_id": "@types/node", "versions": {"24.0.0": {}}}, ensure_ascii=False),
                )
            }
        )

        with patch.object(npm_index, "connect_postgres", return_value=connection):
            with npm_index.serve_packument_shim(
                dsn="postgresql://example",
                table_name="npm_metadata",
                upstream_base_url=None,
                fallback_to_online=False,
            ) as shim:
                with closing(urlopen(f"{shim.base_url}/@types%2Fnode")) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    source = response.headers.get("X-OpenDep-Packument-Source")

        self.assertEqual(payload["_id"], "@types/node")
        self.assertEqual(source, "indexed-postgres")
        self.assertTrue(connection.closed)
        self.assertEqual(connection.executed[0][1], ("@types/node",))

    def test_packument_shim_falls_back_to_online_registry(self) -> None:
        connection = FakeConnection(rows={"left-pad": None})

        with patch.object(npm_index, "connect_postgres", return_value=connection), patch.object(
            npm_index, "UpstreamRegistryClient", FakeUpstreamRegistryClient
        ):
            with npm_index.serve_packument_shim(
                dsn="postgresql://example",
                table_name="npm_metadata",
                upstream_base_url="https://registry.example.test",
                fallback_to_online=True,
            ) as shim:
                with closing(urlopen(f"{shim.base_url}/left-pad")) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    source = response.headers.get("X-OpenDep-Packument-Source")

        self.assertEqual(payload["_id"], "left-pad")
        self.assertEqual(source, "fallback-online")


if __name__ == "__main__":
    unittest.main()
