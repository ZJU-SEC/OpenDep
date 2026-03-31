from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from unittest.mock import patch

from support import PROJECT_ROOT

from adapters.changes_client import NpmChangeEvent, NpmChangesBatch
from pipeline.records import NpmSyncCheckpointRecord

import sync as npm_sync


class FakeMetadataLoader:
    existing_source_revs: dict[str, str | None] = {}
    instances: list["FakeMetadataLoader"] = []

    def __init__(self, *, dsn=None, table_name=None, schema_file=None, connection=None) -> None:
        self.dsn = dsn
        self.table_name = table_name or "npm_metadata"
        self.schema_file = schema_file
        self.connection = connection
        self.ensure_schema_called = False
        self.closed = False
        self.applied_batches: list[tuple[list[object], object, object]] = []
        FakeMetadataLoader.instances.append(self)

    def ensure_schema(self) -> None:
        self.ensure_schema_called = True

    def table_exists(self) -> bool:
        return True

    def get_package_source_rev(self, package_name: str) -> str | None:
        return self.existing_source_revs.get(package_name)

    def apply_sync_batch(self, *, records, checkpoint, sync_state_loader, tombstones=(), tombstone_loader=None) -> None:
        self.applied_batches.append((list(records), list(tombstones), checkpoint, sync_state_loader, tombstone_loader))

    def close(self) -> None:
        self.closed = True


class FakeSyncStateLoader:
    checkpoint: NpmSyncCheckpointRecord | None = None
    instances: list["FakeSyncStateLoader"] = []

    def __init__(self, *, dsn=None, table_name=None, schema_file=None, connection=None) -> None:
        self.dsn = dsn
        self.table_name = table_name or "npm_sync_state"
        self.schema_file = schema_file
        self.connection = connection
        self.ensure_schema_called = False
        self.closed = False
        FakeSyncStateLoader.instances.append(self)

    def ensure_schema(self) -> None:
        self.ensure_schema_called = True

    def table_exists(self) -> bool:
        return True

    def get_checkpoint(self, source_key: str):
        return self.checkpoint

    def close(self) -> None:
        self.closed = True


class FakeTombstoneLoader:
    instances: list["FakeTombstoneLoader"] = []

    def __init__(self, *, dsn=None, table_name=None, schema_file=None, connection=None) -> None:
        self.dsn = dsn
        self.table_name = table_name or "npm_tombstones"
        self.schema_file = schema_file
        self.connection = connection
        self.ensure_schema_called = False
        self.closed = False
        FakeTombstoneLoader.instances.append(self)

    def ensure_schema(self) -> None:
        self.ensure_schema_called = True

    def table_exists(self) -> bool:
        return True

    def close(self) -> None:
        self.closed = True


class FakeChangesClient:
    batch: NpmChangesBatch | None = None
    instances: list["FakeChangesClient"] = []

    def __init__(self, *, changes_url: str) -> None:
        self.changes_url = changes_url.rstrip("/")
        self.fetch_calls: list[tuple[str | None, int]] = []
        FakeChangesClient.instances.append(self)

    def fetch_changes_batch(self, *, since: str | None = None, limit: int = 1000) -> NpmChangesBatch:
        self.fetch_calls.append((since, limit))
        assert self.batch is not None
        return self.batch


class FakeRegistryClient:
    downloads: dict[str, object] = {}
    instances: list["FakeRegistryClient"] = []

    def __init__(self, *, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.fetch_calls: list[str] = []
        FakeRegistryClient.instances.append(self)

    def fetch_raw_packument(self, package_name: str):
        self.fetch_calls.append(package_name)
        value = self.downloads[package_name]
        if isinstance(value, Exception):
            raise value
        return value


class SyncCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeMetadataLoader.existing_source_revs = {}
        FakeMetadataLoader.instances = []
        FakeSyncStateLoader.checkpoint = None
        FakeSyncStateLoader.instances = []
        FakeTombstoneLoader.instances = []
        FakeChangesClient.batch = None
        FakeChangesClient.instances = []
        FakeRegistryClient.downloads = {}
        FakeRegistryClient.instances = []

    def test_sync_once_uses_checkpoint_deduplicates_events_and_advances_checkpoint(self) -> None:
        FakeSyncStateLoader.checkpoint = NpmSyncCheckpointRecord(
            source_key="npmjs-primary",
            registry_base_url="https://replicate.npmjs.com/registry",
            changes_url="https://replicate.npmjs.com/registry/_changes",
            last_seq="41-g1AAAA",
            checkpointed_at=datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc),
        )
        FakeMetadataLoader.existing_source_revs = {"@types/node": "3-cached"}
        FakeChangesClient.batch = NpmChangesBatch(
            events=[
                NpmChangeEvent(package_name="left-pad", sequence="101-g1", changes_rev="1-old"),
                NpmChangeEvent(package_name="is-odd", sequence="102-g1", changes_rev="2-del", deleted=True),
                NpmChangeEvent(package_name="left-pad", sequence="103-g1", changes_rev="3-new"),
                NpmChangeEvent(package_name="@types/node", sequence="104-g1", changes_rev="3-cached"),
            ],
            last_seq="104-g1",
            source_url="https://replicate.npmjs.com/registry/_changes?limit=1000&last-event-id=41-g1AAAA",
        )
        FakeRegistryClient.downloads = {
            "left-pad": type(
                "Download",
                (),
                {
                    "name": "left-pad",
                    "raw_packument": '{"_id":"left-pad","versions":{"1.3.0":{}}}',
                    "source_url": "https://replicate.npmjs.com/registry/left-pad",
                    "source_rev": None,
                    "fetched_at": datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
                },
            )()
        }
        stdout = io.StringIO()

        with patch.object(npm_sync, "NpmPackumentPostgresLoader", FakeMetadataLoader), patch.object(
            npm_sync, "NpmSyncStatePostgresLoader", FakeSyncStateLoader
        ), patch.object(
            npm_sync, "NpmTombstonePostgresLoader", FakeTombstoneLoader
        ), patch.object(npm_sync, "NpmChangesClient", FakeChangesClient), patch.object(
            npm_sync, "NpmRegistryClient", FakeRegistryClient
        ), redirect_stdout(stdout):
            exit_code = npm_sync.main(["sync-once", "--source-key", "npmjs-primary"])

        payload = json.loads(stdout.getvalue())
        metadata_loader = FakeMetadataLoader.instances[0]
        changes_client = FakeChangesClient.instances[0]
        registry_client = FakeRegistryClient.instances[0]

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["input_count"], 4)
        self.assertEqual(payload["requested_count"], 3)
        self.assertEqual(payload["summary"]["fetched_package_count"], 1)
        self.assertEqual(payload["summary"]["updated_row_count"], 1)
        self.assertEqual(payload["summary"]["skipped_row_count"], 1)
        self.assertEqual(payload["summary"]["delete_event_count"], 1)
        self.assertTrue(payload["summary"]["checkpoint_advanced"])
        self.assertEqual(changes_client.fetch_calls, [("41-g1AAAA", 1000)])
        self.assertEqual(registry_client.fetch_calls, ["left-pad"])
        self.assertEqual(len(metadata_loader.applied_batches), 1)

        records, tombstones, checkpoint, _, tombstone_loader = metadata_loader.applied_batches[0]
        self.assertEqual(len(records), 1)
        self.assertEqual(len(tombstones), 1)
        self.assertEqual(records[0].name, "left-pad")
        self.assertEqual(records[0].source_rev, "3-new")
        self.assertEqual(tombstones[0].name, "is-odd")
        self.assertEqual(checkpoint.last_seq, "104-g1")
        self.assertIsNotNone(tombstone_loader)

        statuses = {item["name"]: item["status"] for item in payload["results"]}
        self.assertEqual(statuses["left-pad"], "updated")
        self.assertEqual(statuses["is-odd"], "deleted")
        self.assertEqual(statuses["@types/node"], "skipped")
        self.assertTrue(metadata_loader.closed)
        self.assertTrue(FakeSyncStateLoader.instances[0].closed)
        self.assertTrue(FakeTombstoneLoader.instances[0].closed)

    def test_sync_once_does_not_advance_checkpoint_when_fetch_fails(self) -> None:
        FakeChangesClient.batch = NpmChangesBatch(
            events=[
                NpmChangeEvent(package_name="left-pad", sequence="101-g1", changes_rev="1-new"),
            ],
            last_seq="101-g1",
            source_url="https://replicate.npmjs.com/registry/_changes?limit=1000",
        )
        FakeRegistryClient.downloads = {
            "left-pad": RuntimeError("registry temporarily unavailable"),
        }
        stdout = io.StringIO()

        with patch.object(npm_sync, "NpmPackumentPostgresLoader", FakeMetadataLoader), patch.object(
            npm_sync, "NpmSyncStatePostgresLoader", FakeSyncStateLoader
        ), patch.object(
            npm_sync, "NpmTombstonePostgresLoader", FakeTombstoneLoader
        ), patch.object(npm_sync, "NpmChangesClient", FakeChangesClient), patch.object(
            npm_sync, "NpmRegistryClient", FakeRegistryClient
        ), redirect_stdout(stdout):
            exit_code = npm_sync.main(["sync-once", "--source-key", "npmjs-primary", "--since", "100-g1"])

        payload = json.loads(stdout.getvalue())
        metadata_loader = FakeMetadataLoader.instances[0]
        changes_client = FakeChangesClient.instances[0]

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["summary"]["error_count"], 1)
        self.assertFalse(payload["summary"]["checkpoint_advanced"])
        self.assertEqual(changes_client.fetch_calls, [("100-g1", 1000)])
        self.assertEqual(len(metadata_loader.applied_batches), 0)
        self.assertIn("checkpoint was not advanced", payload["warnings"][0])

    def test_sync_follow_accumulates_metrics_and_stops_gracefully(self) -> None:
        outcomes = [
            npm_sync.SyncRunOutcome(
                exit_code=0,
                payload={
                    "status": "ok",
                    "operation": "sync-once",
                    "summary": {
                        "fetched_package_count": 0,
                        "updated_row_count": 0,
                        "skipped_row_count": 0,
                        "delete_event_count": 0,
                        "error_count": 0,
                        "checkpoint_advanced": False,
                    },
                    "source": {"last_seq": "100-g1"},
                },
            ),
            npm_sync.SyncRunOutcome(
                exit_code=1,
                payload={
                    "status": "error",
                    "operation": "sync-once",
                    "message": "temporary registry failure",
                    "summary": {
                        "fetched_package_count": 0,
                        "updated_row_count": 0,
                        "skipped_row_count": 0,
                        "delete_event_count": 0,
                        "error_count": 1,
                        "checkpoint_advanced": False,
                    },
                },
                retryable=True,
            ),
            npm_sync.SyncRunOutcome(
                exit_code=0,
                payload={
                    "status": "ok",
                    "operation": "sync-once",
                    "summary": {
                        "fetched_package_count": 2,
                        "updated_row_count": 2,
                        "skipped_row_count": 1,
                        "delete_event_count": 1,
                        "error_count": 0,
                        "checkpoint_advanced": True,
                    },
                    "source": {"last_seq": "101-g1"},
                },
            ),
        ]
        stdout = io.StringIO()

        with patch.object(npm_sync, "run_sync_once_command", side_effect=outcomes), patch.object(
            npm_sync.time, "sleep", side_effect=[None, None, KeyboardInterrupt()]
        ), redirect_stdout(stdout):
            exit_code = npm_sync.main(
                [
                    "sync-follow",
                    "--source-key",
                    "npmjs-primary",
                    "--poll-interval",
                    "5",
                    "--idle-backoff",
                    "10",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["summary"]["processed_batch_count"], 3)
        self.assertEqual(payload["summary"]["advanced_checkpoint_count"], 1)
        self.assertEqual(payload["summary"]["idle_poll_count"], 1)
        self.assertEqual(payload["summary"]["transient_failure_count"], 1)
        self.assertEqual(payload["summary"]["updated_row_count"], 2)
        self.assertEqual(payload["summary"]["skipped_row_count"], 1)
        self.assertEqual(payload["summary"]["delete_event_count"], 1)
        self.assertEqual(payload["source"]["concurrency"], 4)
        self.assertIn("stopped gracefully", payload["warnings"][0])


if __name__ == "__main__":
    unittest.main()
