from __future__ import annotations

import unittest
from datetime import datetime, timezone

from support import PROJECT_ROOT

from loaders.postgres_loader import NpmPackumentPostgresLoader, NpmSyncStatePostgresLoader, NpmTombstonePostgresLoader
from pipeline.records import NpmPackumentRecord, NpmSyncCheckpointRecord, NpmTombstoneRecord


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
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        self.closed = True


class PostgresLoaderTests(unittest.TestCase):
    def test_upsert_record_executes_expected_query(self) -> None:
        connection = FakeConnection()
        loader = NpmPackumentPostgresLoader(connection=connection)
        record = NpmPackumentRecord.from_raw_packument(
            name="@types/node",
            raw_packument='{"_id":"@types/node","versions":{}}',
            source_url="https://registry.example.test/@types%2Fnode",
            source_rev="1-abc",
            fetched_at=datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
        )

        loader.upsert_record(record)

        self.assertEqual(connection.commit_count, 1)
        self.assertEqual(connection.rollback_count, 0)
        self.assertEqual(len(connection.executed), 1)
        query, params = connection.executed[0]
        self.assertIn("INSERT INTO npm_metadata", query)
        self.assertIn("ON CONFLICT (name) DO UPDATE SET", query)
        self.assertIn("updated_at = NOW()", query)
        self.assertEqual(
            params,
            (
                "@types/node",
                '{"_id":"@types/node","versions":{}}',
                record.raw_packument_sha256,
                "https://registry.example.test/@types%2Fnode",
                "1-abc",
                datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
            ),
        )

    def test_get_checkpoint_returns_record(self) -> None:
        connection = FakeConnection()
        connection.fetchone_result = (
            "npmjs-primary",
            "https://registry.npmjs.org",
            "https://replicate.npmjs.com/_changes",
            "12345-g1AAAA",
            datetime(2026, 4, 15, 13, 0, tzinfo=timezone.utc),
        )
        loader = NpmSyncStatePostgresLoader(connection=connection)

        checkpoint = loader.get_checkpoint("npmjs-primary")

        self.assertIsNotNone(checkpoint)
        assert checkpoint is not None
        self.assertEqual(checkpoint.source_key, "npmjs-primary")
        self.assertEqual(checkpoint.last_seq, "12345-g1AAAA")
        self.assertEqual(connection.executed[0][1], ("npmjs-primary",))

    def test_get_package_source_rev_returns_value(self) -> None:
        connection = FakeConnection()
        connection.fetchone_result = ("12345-g1AAAA",)
        loader = NpmPackumentPostgresLoader(connection=connection)

        source_rev = loader.get_package_source_rev("left-pad")

        self.assertEqual(source_rev, "12345-g1AAAA")
        self.assertEqual(connection.executed[0][1], ("left-pad",))

    def test_initialize_checkpoint_executes_insert_only_query(self) -> None:
        connection = FakeConnection()
        loader = NpmSyncStatePostgresLoader(connection=connection)
        checkpoint = NpmSyncCheckpointRecord(
            source_key="npmjs-primary",
            registry_base_url="https://registry.npmjs.org",
            changes_url="https://replicate.npmjs.com/_changes",
            last_seq=None,
            checkpointed_at=None,
        )

        loader.initialize_checkpoint(checkpoint)

        self.assertEqual(connection.commit_count, 1)
        query, params = connection.executed[0]
        self.assertIn("INSERT INTO npm_sync_state", query)
        self.assertIn("ON CONFLICT (source_key) DO NOTHING", query)
        self.assertEqual(
            params,
            (
                "npmjs-primary",
                "https://registry.npmjs.org",
                "https://replicate.npmjs.com/_changes",
                None,
                None,
            ),
        )

    def test_update_checkpoint_executes_expected_query(self) -> None:
        connection = FakeConnection()
        loader = NpmSyncStatePostgresLoader(connection=connection)
        checkpoint = NpmSyncCheckpointRecord(
            source_key="npmjs-primary",
            registry_base_url="https://registry.npmjs.org",
            changes_url="https://replicate.npmjs.com/_changes",
            last_seq="12345-g1AAAA",
            checkpointed_at=datetime(2026, 4, 15, 13, 0, tzinfo=timezone.utc),
        )

        loader.update_checkpoint(checkpoint)

        self.assertEqual(connection.commit_count, 1)
        query, params = connection.executed[0]
        self.assertIn("UPDATE npm_sync_state SET", query)
        self.assertIn("updated_at = NOW()", query)
        self.assertEqual(
            params,
            (
                "https://registry.npmjs.org",
                "https://replicate.npmjs.com/_changes",
                "12345-g1AAAA",
                datetime(2026, 4, 15, 13, 0, tzinfo=timezone.utc),
                "npmjs-primary",
            ),
        )

    def test_apply_sync_batch_keeps_packuments_and_checkpoint_in_one_transaction(self) -> None:
        connection = FakeConnection()
        packument_loader = NpmPackumentPostgresLoader(connection=connection)
        sync_loader = NpmSyncStatePostgresLoader(connection=connection)
        record = NpmPackumentRecord.from_raw_packument(
            name="left-pad",
            raw_packument='{"_id":"left-pad","versions":{"1.3.0":{}}}',
            source_url="https://registry.example.test/left-pad",
            source_rev="10-abc",
            fetched_at=datetime(2026, 4, 15, 12, 30, tzinfo=timezone.utc),
        )
        checkpoint = NpmSyncCheckpointRecord(
            source_key="npmjs-primary",
            registry_base_url="https://registry.npmjs.org",
            changes_url="https://replicate.npmjs.com/_changes",
            last_seq="12346-g1BBBB",
            checkpointed_at=datetime(2026, 4, 15, 12, 31, tzinfo=timezone.utc),
        )

        packument_loader.apply_sync_batch(records=[record], checkpoint=checkpoint, sync_state_loader=sync_loader)

        self.assertEqual(connection.commit_count, 1)
        self.assertEqual(connection.rollback_count, 0)
        self.assertEqual(len(connection.executed), 2)

        record_query, record_params = connection.executed[0]
        checkpoint_query, checkpoint_params = connection.executed[1]

        self.assertIn("INSERT INTO npm_metadata", record_query)
        self.assertEqual(record_params[0], "left-pad")
        self.assertIn("INSERT INTO npm_sync_state", checkpoint_query)
        self.assertIn("ON CONFLICT (source_key) DO UPDATE SET", checkpoint_query)
        self.assertEqual(
            checkpoint_params,
            (
                "npmjs-primary",
                "https://registry.npmjs.org",
                "https://replicate.npmjs.com/_changes",
                "12346-g1BBBB",
                datetime(2026, 4, 15, 12, 31, tzinfo=timezone.utc),
            ),
        )

    def test_upsert_tombstone_executes_expected_query(self) -> None:
        connection = FakeConnection()
        loader = NpmTombstonePostgresLoader(connection=connection)
        tombstone = NpmTombstoneRecord(
            name="left-pad",
            source_rev="44-deleted",
            deleted_seq="12346-g1BBBB",
            deleted_at=datetime(2026, 4, 15, 12, 31, tzinfo=timezone.utc),
        )

        loader.upsert_tombstone(tombstone)

        self.assertEqual(connection.commit_count, 1)
        query, params = connection.executed[0]
        self.assertIn("INSERT INTO npm_tombstones", query)
        self.assertIn("ON CONFLICT (name) DO UPDATE SET", query)
        self.assertEqual(
            params,
            (
                "left-pad",
                "44-deleted",
                "12346-g1BBBB",
                datetime(2026, 4, 15, 12, 31, tzinfo=timezone.utc),
            ),
        )

    def test_apply_sync_batch_handles_tombstones_and_restore_cleanup(self) -> None:
        connection = FakeConnection()
        packument_loader = NpmPackumentPostgresLoader(connection=connection)
        sync_loader = NpmSyncStatePostgresLoader(connection=connection)
        tombstone_loader = NpmTombstonePostgresLoader(connection=connection)
        record = NpmPackumentRecord.from_raw_packument(
            name="left-pad",
            raw_packument='{"_id":"left-pad","versions":{"1.3.0":{}}}',
            source_url="https://registry.example.test/left-pad",
            source_rev="10-abc",
            fetched_at=datetime(2026, 4, 15, 12, 30, tzinfo=timezone.utc),
        )
        tombstone = NpmTombstoneRecord(
            name="is-odd",
            source_rev="11-deleted",
            deleted_seq="12346-g1BBBB",
            deleted_at=datetime(2026, 4, 15, 12, 31, tzinfo=timezone.utc),
        )
        checkpoint = NpmSyncCheckpointRecord(
            source_key="npmjs-primary",
            registry_base_url="https://registry.npmjs.org",
            changes_url="https://replicate.npmjs.com/_changes",
            last_seq="12346-g1BBBB",
            checkpointed_at=datetime(2026, 4, 15, 12, 31, tzinfo=timezone.utc),
        )

        packument_loader.apply_sync_batch(
            records=[record],
            tombstones=[tombstone],
            checkpoint=checkpoint,
            sync_state_loader=sync_loader,
            tombstone_loader=tombstone_loader,
        )

        self.assertEqual(connection.commit_count, 1)
        self.assertEqual(len(connection.executed), 5)
        self.assertIn("INSERT INTO npm_metadata", connection.executed[0][0])
        self.assertIn("DELETE FROM npm_tombstones", connection.executed[1][0])
        self.assertEqual(connection.executed[1][1], ("left-pad",))
        self.assertIn("DELETE FROM npm_metadata", connection.executed[2][0])
        self.assertEqual(connection.executed[2][1], ("is-odd",))
        self.assertIn("INSERT INTO npm_tombstones", connection.executed[3][0])
        self.assertIn("INSERT INTO npm_sync_state", connection.executed[4][0])


if __name__ == "__main__":
    unittest.main()
