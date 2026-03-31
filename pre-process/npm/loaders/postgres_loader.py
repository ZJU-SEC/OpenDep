from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Sequence


CURRENT_FILE = Path(__file__).resolve()
NPM_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]
COMMON_DATABASE_ROOT = PROJECT_ROOT / "pre-process" / "common" / "database"

for path in (NPM_ROOT, PROJECT_ROOT, COMMON_DATABASE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from pipeline.records import NpmPackumentRecord, NpmSyncCheckpointRecord, NpmTombstoneRecord
from postgres import connect_postgres, execute_sql_file, postgres_cursor, postgres_transaction


DEFAULT_TABLE_NAME = "npm_metadata"
DEFAULT_SCHEMA_FILE = PROJECT_ROOT / "pre-process" / "common" / "database" / "initdb" / "20-npm-metadata.sql"
DEFAULT_SYNC_STATE_TABLE_NAME = "npm_sync_state"
DEFAULT_SYNC_STATE_SCHEMA_FILE = PROJECT_ROOT / "pre-process" / "common" / "database" / "initdb" / "21-npm-sync-state.sql"
DEFAULT_TOMBSTONE_TABLE_NAME = "npm_tombstones"
DEFAULT_TOMBSTONE_SCHEMA_FILE = PROJECT_ROOT / "pre-process" / "common" / "database" / "initdb" / "22-npm-tombstones.sql"


class NpmPackumentPostgresLoader:
    def __init__(
        self,
        *,
        dsn: str | None = None,
        table_name: str = DEFAULT_TABLE_NAME,
        schema_file: str | Path = DEFAULT_SCHEMA_FILE,
        connection: Any | None = None,
    ) -> None:
        self._dsn = dsn
        self._table_name = table_name
        self._schema_file = Path(schema_file)
        self._connection = connection

    @property
    def table_name(self) -> str:
        return self._table_name

    def ensure_schema(self) -> None:
        execute_sql_file(self._connect(), self._schema_file)

    def table_exists(self) -> bool:
        query = "SELECT to_regclass(%s)"
        params = (self._table_name,)
        connection = self._connect()
        with postgres_cursor(connection) as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
            return bool(row and row[0])

    def has_package(self, package_name: str) -> bool:
        query = f"SELECT 1 FROM {self._table_name} WHERE name = %s LIMIT 1"
        params = (package_name,)
        connection = self._connect()
        with postgres_cursor(connection) as cursor:
            cursor.execute(query, params)
            return cursor.fetchone() is not None

    def get_package_source_rev(self, package_name: str) -> str | None:
        query = f"SELECT source_rev FROM {self._table_name} WHERE name = %s LIMIT 1"
        params = (package_name,)
        connection = self._connect()
        with postgres_cursor(connection) as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        if row is None:
            return None
        return row[0]

    def upsert_record(self, record: NpmPackumentRecord) -> None:
        connection = self._connect()
        with postgres_transaction(connection):
            with postgres_cursor(connection) as cursor:
                self._upsert_record_cursor(cursor, record)

    def upsert_records(self, records: Sequence[NpmPackumentRecord]) -> None:
        connection = self._connect()
        with postgres_transaction(connection):
            with postgres_cursor(connection) as cursor:
                for record in records:
                    self._upsert_record_cursor(cursor, record)

    def apply_sync_batch(
        self,
        *,
        records: Sequence[NpmPackumentRecord],
        checkpoint: NpmSyncCheckpointRecord,
        sync_state_loader: "NpmSyncStatePostgresLoader",
        tombstones: Sequence[NpmTombstoneRecord] = (),
        tombstone_loader: "NpmTombstonePostgresLoader | None" = None,
    ) -> None:
        connection = self._connect()
        with postgres_transaction(connection):
            with postgres_cursor(connection) as cursor:
                for record in records:
                    self._upsert_record_cursor(cursor, record)
                    if tombstone_loader is not None:
                        tombstone_loader._delete_tombstone_cursor(cursor, record.name)
                for tombstone in tombstones:
                    self._delete_package_cursor(cursor, tombstone.name)
                    if tombstone_loader is not None:
                        tombstone_loader._upsert_tombstone_cursor(cursor, tombstone)
                sync_state_loader._upsert_checkpoint_cursor(cursor, checkpoint)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _connect(self):
        if self._connection is None:
            self._connection = connect_postgres(self._dsn)
        return self._connection

    def _upsert_record_cursor(self, cursor: Any, record: NpmPackumentRecord) -> None:
        query = (
            f"INSERT INTO {self._table_name} "
            "(name, raw_packument, raw_packument_sha256, source_url, source_rev, fetched_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (name) DO UPDATE SET "
            "raw_packument = EXCLUDED.raw_packument, "
            "raw_packument_sha256 = EXCLUDED.raw_packument_sha256, "
            "source_url = EXCLUDED.source_url, "
            "source_rev = EXCLUDED.source_rev, "
            "fetched_at = EXCLUDED.fetched_at, "
            "updated_at = NOW()"
        )
        params = (
            record.name,
            record.raw_packument,
            record.raw_packument_sha256,
            record.source_url,
            record.source_rev,
            record.fetched_at,
        )
        cursor.execute(query, params)

    def _delete_package_cursor(self, cursor: Any, package_name: str) -> None:
        cursor.execute(
            f"DELETE FROM {self._table_name} WHERE name = %s",
            (package_name,),
        )


class NpmSyncStatePostgresLoader:
    def __init__(
        self,
        *,
        dsn: str | None = None,
        table_name: str = DEFAULT_SYNC_STATE_TABLE_NAME,
        schema_file: str | Path = DEFAULT_SYNC_STATE_SCHEMA_FILE,
        connection: Any | None = None,
    ) -> None:
        self._dsn = dsn
        self._table_name = table_name
        self._schema_file = Path(schema_file)
        self._connection = connection

    @property
    def table_name(self) -> str:
        return self._table_name

    def ensure_schema(self) -> None:
        execute_sql_file(self._connect(), self._schema_file)

    def table_exists(self) -> bool:
        query = "SELECT to_regclass(%s)"
        params = (self._table_name,)
        connection = self._connect()
        with postgres_cursor(connection) as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
            return bool(row and row[0])

    def get_checkpoint(self, source_key: str) -> NpmSyncCheckpointRecord | None:
        query = (
            f"SELECT source_key, registry_base_url, changes_url, last_seq, checkpointed_at "
            f"FROM {self._table_name} WHERE source_key = %s LIMIT 1"
        )
        params = (source_key,)
        connection = self._connect()
        with postgres_cursor(connection) as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        if row is None:
            return None
        return NpmSyncCheckpointRecord(
            source_key=row[0],
            registry_base_url=row[1],
            changes_url=row[2],
            last_seq=row[3],
            checkpointed_at=row[4],
        )

    def initialize_checkpoint(self, checkpoint: NpmSyncCheckpointRecord) -> None:
        connection = self._connect()
        with postgres_transaction(connection):
            with postgres_cursor(connection) as cursor:
                self._initialize_checkpoint_cursor(cursor, checkpoint)

    def update_checkpoint(self, checkpoint: NpmSyncCheckpointRecord) -> None:
        connection = self._connect()
        with postgres_transaction(connection):
            with postgres_cursor(connection) as cursor:
                self._update_checkpoint_cursor(cursor, checkpoint)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _connect(self):
        if self._connection is None:
            self._connection = connect_postgres(self._dsn)
        return self._connection

    def _initialize_checkpoint_cursor(self, cursor: Any, checkpoint: NpmSyncCheckpointRecord) -> None:
        query = (
            f"INSERT INTO {self._table_name} "
            "(source_key, registry_base_url, changes_url, last_seq, checkpointed_at) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (source_key) DO NOTHING"
        )
        params = (
            checkpoint.source_key,
            checkpoint.registry_base_url,
            checkpoint.changes_url,
            checkpoint.last_seq,
            checkpoint.checkpointed_at,
        )
        cursor.execute(query, params)

    def _update_checkpoint_cursor(self, cursor: Any, checkpoint: NpmSyncCheckpointRecord) -> None:
        query = (
            f"UPDATE {self._table_name} SET "
            "registry_base_url = %s, "
            "changes_url = %s, "
            "last_seq = %s, "
            "checkpointed_at = %s, "
            "updated_at = NOW() "
            "WHERE source_key = %s"
        )
        params = (
            checkpoint.registry_base_url,
            checkpoint.changes_url,
            checkpoint.last_seq,
            checkpoint.checkpointed_at,
            checkpoint.source_key,
        )
        cursor.execute(query, params)

    def _upsert_checkpoint_cursor(self, cursor: Any, checkpoint: NpmSyncCheckpointRecord) -> None:
        query = (
            f"INSERT INTO {self._table_name} "
            "(source_key, registry_base_url, changes_url, last_seq, checkpointed_at) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (source_key) DO UPDATE SET "
            "registry_base_url = EXCLUDED.registry_base_url, "
            "changes_url = EXCLUDED.changes_url, "
            "last_seq = EXCLUDED.last_seq, "
            "checkpointed_at = EXCLUDED.checkpointed_at, "
            "updated_at = NOW()"
        )
        params = (
            checkpoint.source_key,
            checkpoint.registry_base_url,
            checkpoint.changes_url,
            checkpoint.last_seq,
            checkpoint.checkpointed_at,
        )
        cursor.execute(query, params)


class NpmTombstonePostgresLoader:
    def __init__(
        self,
        *,
        dsn: str | None = None,
        table_name: str = DEFAULT_TOMBSTONE_TABLE_NAME,
        schema_file: str | Path = DEFAULT_TOMBSTONE_SCHEMA_FILE,
        connection: Any | None = None,
    ) -> None:
        self._dsn = dsn
        self._table_name = table_name
        self._schema_file = Path(schema_file)
        self._connection = connection

    @property
    def table_name(self) -> str:
        return self._table_name

    def ensure_schema(self) -> None:
        execute_sql_file(self._connect(), self._schema_file)

    def table_exists(self) -> bool:
        query = "SELECT to_regclass(%s)"
        params = (self._table_name,)
        connection = self._connect()
        with postgres_cursor(connection) as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
            return bool(row and row[0])

    def get_tombstone(self, package_name: str) -> NpmTombstoneRecord | None:
        query = (
            f"SELECT name, source_rev, deleted_seq, deleted_at "
            f"FROM {self._table_name} WHERE name = %s LIMIT 1"
        )
        params = (package_name,)
        connection = self._connect()
        with postgres_cursor(connection) as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        if row is None:
            return None
        return NpmTombstoneRecord(
            name=row[0],
            source_rev=row[1],
            deleted_seq=row[2],
            deleted_at=row[3],
        )

    def upsert_tombstone(self, tombstone: NpmTombstoneRecord) -> None:
        connection = self._connect()
        with postgres_transaction(connection):
            with postgres_cursor(connection) as cursor:
                self._upsert_tombstone_cursor(cursor, tombstone)

    def delete_tombstone(self, package_name: str) -> None:
        connection = self._connect()
        with postgres_transaction(connection):
            with postgres_cursor(connection) as cursor:
                self._delete_tombstone_cursor(cursor, package_name)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _connect(self):
        if self._connection is None:
            self._connection = connect_postgres(self._dsn)
        return self._connection

    def _upsert_tombstone_cursor(self, cursor: Any, tombstone: NpmTombstoneRecord) -> None:
        query = (
            f"INSERT INTO {self._table_name} "
            "(name, source_rev, deleted_seq, deleted_at) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (name) DO UPDATE SET "
            "source_rev = EXCLUDED.source_rev, "
            "deleted_seq = EXCLUDED.deleted_seq, "
            "deleted_at = EXCLUDED.deleted_at, "
            "updated_at = NOW()"
        )
        params = (
            tombstone.name,
            tombstone.source_rev,
            tombstone.deleted_seq,
            tombstone.deleted_at,
        )
        cursor.execute(query, params)

    def _delete_tombstone_cursor(self, cursor: Any, package_name: str) -> None:
        cursor.execute(
            f"DELETE FROM {self._table_name} WHERE name = %s",
            (package_name,),
        )
