from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    from packaging.utils import canonicalize_name
except ImportError:  # pragma: no cover
    from pip._vendor.packaging.utils import canonicalize_name


CURRENT_FILE = Path(__file__).resolve()
PIP_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]
COMMON_DATABASE_ROOT = PROJECT_ROOT / "pre-process" / "common" / "database"

for path in (PIP_ROOT, PROJECT_ROOT, COMMON_DATABASE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from pip_models import ExtractedMetadataRecord
from postgres import connect_postgres, execute_sql_file, postgres_cursor, postgres_transaction


DEFAULT_TABLE_NAME = "pip_projects_metadata"
DEFAULT_SCHEMA_FILE = PROJECT_ROOT / "pre-process" / "common" / "database" / "initdb" / "00-pip-projects-metadata.sql"


class PipMetadataPostgresLoader:
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

    def has_release(self, project_name: str, version: str) -> bool:
        query = f"SELECT 1 FROM {self._table_name} WHERE name = %s AND version = %s LIMIT 1"
        params = (canonicalize_name(project_name), version)
        connection = self._connect()
        with postgres_cursor(connection) as cursor:
            cursor.execute(query, params)
            return cursor.fetchone() is not None

    def list_versions(self, project_name: str) -> tuple[str, ...]:
        query = f"SELECT version FROM {self._table_name} WHERE name = %s"
        params = (canonicalize_name(project_name),)
        connection = self._connect()
        with postgres_cursor(connection) as cursor:
            cursor.execute(query, params)
            return tuple(str(row[0]) for row in cursor.fetchall() if row and row[0] is not None)

    def upsert_record(self, record: ExtractedMetadataRecord) -> None:
        metadata_payload = {
            "requires_python": record.requires_python,
            "artifact_path": record.artifact_path,
            "artifact_kind": record.artifact_kind,
            "artifact_filename": record.artifact_filename,
            "artifact_url": record.artifact_url,
            "artifact_hash": record.artifact_hash,
            "extracted_at": record.extracted_at,
            "dependency_source_detail": record.dependency_source_detail,
            "parse_warnings": list(record.parse_warnings),
            "source_kind": record.source_kind,
            "extraction_backend": record.extraction_backend,
        }
        dependency_json = json.dumps(list(record.requires_dist), ensure_ascii=False)
        metadata_json = json.dumps(metadata_payload, ensure_ascii=False)

        query = (
            f"INSERT INTO {self._table_name} "
            "(name, version, dependency, yanked, metadata, parsed_type_for_dep, version_struct) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (name, version) DO UPDATE SET "
            "dependency = EXCLUDED.dependency, "
            "yanked = EXCLUDED.yanked, "
            "metadata = EXCLUDED.metadata, "
            "parsed_type_for_dep = EXCLUDED.parsed_type_for_dep, "
            "version_struct = EXCLUDED.version_struct"
        )
        params = (
            canonicalize_name(record.name),
            record.version,
            dependency_json,
            record.yanked,
            metadata_json,
            record.source_kind,
            record.version,
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
