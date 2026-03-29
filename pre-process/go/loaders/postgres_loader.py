from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


CURRENT_FILE = Path(__file__).resolve()
GO_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]
COMMON_DATABASE_ROOT = PROJECT_ROOT / "pre-process" / "common" / "database"

for path in (GO_ROOT, PROJECT_ROOT, COMMON_DATABASE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from pipeline.records import GoModuleModfileRecord
from postgres import connect_postgres, execute_sql_file, postgres_cursor, postgres_transaction


DEFAULT_TABLE_NAME = "go_metadata"
DEFAULT_SCHEMA_FILE = PROJECT_ROOT / "pre-process" / "common" / "database" / "initdb" / "10-go-metadata.sql"


class GoModuleModfilePostgresLoader:
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

    def has_module(self, module_path: str, version: str) -> bool:
        query = f"SELECT 1 FROM {self._table_name} WHERE module_path = %s AND version = %s LIMIT 1"
        params = (module_path, version)
        connection = self._connect()
        with postgres_cursor(connection) as cursor:
            cursor.execute(query, params)
            return cursor.fetchone() is not None

    def upsert_record(self, record: GoModuleModfileRecord) -> None:
        query = (
            f"INSERT INTO {self._table_name} "
            "(module_path, version, raw_mod, raw_mod_sha256, source_url, fetched_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (module_path, version) DO UPDATE SET "
            "raw_mod = EXCLUDED.raw_mod, "
            "raw_mod_sha256 = EXCLUDED.raw_mod_sha256, "
            "source_url = EXCLUDED.source_url, "
            "fetched_at = EXCLUDED.fetched_at, "
            "updated_at = NOW()"
        )
        params = (
            record.module_path,
            record.version,
            record.raw_mod,
            record.raw_mod_sha256,
            record.source_url,
            record.fetched_at,
        )

        connection = self._connect()
        with postgres_transaction(connection):
            with postgres_cursor(connection) as cursor:
                cursor.execute(query, params)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _connect(self):
        if self._connection is None:
            self._connection = connect_postgres(self._dsn)
        return self._connection
