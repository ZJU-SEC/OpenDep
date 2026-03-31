from __future__ import annotations

import unittest
from datetime import datetime, timezone

from support import PROJECT_ROOT

from loaders.postgres_loader import GoModuleModfilePostgresLoader
from pipeline.records import GoModuleModfileRecord


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self._connection = connection

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, query: str, params=None) -> None:
        self._connection.executed.append((query, params))

    def fetchone(self):
        return self._connection.fetchone_result


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...] | None]] = []
        self.commit_count = 0
        self.rollback_count = 0
        self.fetchone_result = None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        return None


class PostgresLoaderTests(unittest.TestCase):
    def test_upsert_record_executes_expected_query(self) -> None:
        connection = FakeConnection()
        loader = GoModuleModfilePostgresLoader(connection=connection)
        record = GoModuleModfileRecord.from_raw_mod(
            module_path="example.com/module",
            version="v1.2.3",
            raw_mod="module example.com/module\n",
            source_url="https://proxy.example.test/example.com/module/@v/v1.2.3.mod",
            fetched_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
        )

        loader.upsert_record(record)

        self.assertEqual(connection.commit_count, 1)
        self.assertEqual(connection.rollback_count, 0)
        self.assertEqual(len(connection.executed), 1)
        query, params = connection.executed[0]
        self.assertIn("INSERT INTO go_metadata", query)
        self.assertIn("ON CONFLICT (module_path, version) DO UPDATE SET", query)
        self.assertIn("updated_at = NOW()", query)
        self.assertEqual(
            params,
            (
                "example.com/module",
                "v1.2.3",
                "module example.com/module\n",
                record.raw_mod_sha256,
                "https://proxy.example.test/example.com/module/@v/v1.2.3.mod",
                datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
            ),
        )


if __name__ == "__main__":
    unittest.main()
