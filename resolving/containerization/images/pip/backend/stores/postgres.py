from __future__ import annotations

import ast
import json
from typing import Any

try:
    from packaging.utils import canonicalize_name
except ImportError:  # pragma: no cover - fallback for minimal pip environments
    from pip._vendor.packaging.utils import canonicalize_name

from resolving.containerization.images.pip.backend.models import PackageMetadataRecord, VersionRecord
from resolving.containerization.images.pip.backend.stores.base import IndexStore


def _load_driver():
    try:
        import psycopg  # type: ignore

        return "psycopg", psycopg
    except ImportError:
        pass

    try:
        import psycopg2  # type: ignore

        return "psycopg2", psycopg2
    except ImportError as exc:
        raise RuntimeError(
            "PostgresIndexStore requires psycopg or psycopg2 to be installed"
        ) from exc


def _deserialize_dependency(value: object) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, list):
        return tuple(str(entry) for entry in value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ()
        for loader in (json.loads, ast.literal_eval):
            try:
                loaded = loader(stripped)
            except Exception:
                continue
            if isinstance(loaded, list):
                return tuple(str(entry) for entry in loaded)
        return (stripped,)
    return ()


def _deserialize_metadata(value: object) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return {}
        for loader in (json.loads, ast.literal_eval):
            try:
                loaded = loader(stripped)
            except Exception:
                continue
            if isinstance(loaded, dict):
                return {str(key): loaded[key] for key in loaded}
    return {}


class PostgresIndexStore(IndexStore):
    def __init__(self, dsn: str, *, table_name: str = "pip_projects_metadata") -> None:
        self._dsn = dsn
        self._table_name = table_name
        self._driver_name, self._driver = _load_driver()
        self._connection = None

    def list_versions(self, project_name: str) -> list[VersionRecord]:
        normalized_name = canonicalize_name(project_name)
        rows = self._fetchall(
            f"SELECT name, version, yanked, parsed_type_for_dep FROM {self._table_name} WHERE name = %s",
            (normalized_name,),
        )
        records = [
            VersionRecord(
                name=row[0],
                version=row[1],
                yanked=bool(row[2]) if row[2] is not None else False,
                source_kind=row[3],
            )
            for row in rows
            if row[1]
        ]
        return sorted(records, key=self._version_sort_key, reverse=True)

    def get_release(self, project_name: str, version: str) -> PackageMetadataRecord | None:
        normalized_name = canonicalize_name(project_name)
        row = self._fetchone(
            (
                f"SELECT name, version, dependency, yanked, metadata, parsed_type_for_dep "
                f"FROM {self._table_name} WHERE name = %s AND version = %s LIMIT 1"
            ),
            (normalized_name, version),
        )
        if row is None:
            return None
        metadata_payload = _deserialize_metadata(row[4])
        return PackageMetadataRecord(
            name=row[0],
            version=row[1],
            requires_dist=_deserialize_dependency(row[2]),
            requires_python=metadata_payload.get("requires_python"),
            yanked=bool(row[3]) if row[3] is not None else False,
            source_kind=row[5] or metadata_payload.get("source_kind") or "indexed-postgres",
            artifact_url=metadata_payload.get("artifact_url"),
            artifact_hash=metadata_payload.get("artifact_hash"),
            extracted_at=metadata_payload.get("extracted_at"),
            dependency_source_detail=metadata_payload.get("dependency_source_detail"),
            parse_warnings=tuple(str(item) for item in metadata_payload.get("parse_warnings", [])),
        )

    def put_release(self, record: PackageMetadataRecord) -> None:
        connection = self._connect()
        metadata_payload = {
            "requires_python": record.requires_python,
            "artifact_url": record.artifact_url,
            "artifact_hash": record.artifact_hash,
            "extracted_at": record.extracted_at,
            "dependency_source_detail": record.dependency_source_detail,
            "parse_warnings": list(record.parse_warnings),
            "source_kind": record.source_kind,
        }
        dependency_json = json.dumps(list(record.requires_dist), ensure_ascii=False)
        metadata_json = json.dumps(metadata_payload, ensure_ascii=False)

        with connection.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {self._table_name} WHERE name = %s AND version = %s",
                (canonicalize_name(record.name), record.version),
            )
            cursor.execute(
                (
                    f"INSERT INTO {self._table_name} "
                    "(name, version, dependency, yanked, metadata, parsed_type_for_dep, version_struct) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)"
                ),
                (
                    canonicalize_name(record.name),
                    record.version,
                    dependency_json,
                    record.yanked,
                    metadata_json,
                    record.source_kind,
                    record.version,
                ),
            )
        connection.commit()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _connect(self):
        if self._connection is not None:
            return self._connection
        if self._driver_name == "psycopg":
            self._connection = self._driver.connect(self._dsn)
        else:
            self._connection = self._driver.connect(self._dsn)
        return self._connection

    def _fetchall(self, query: str, params: tuple[object, ...]) -> list[tuple]:
        connection = self._connect()
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            return list(cursor.fetchall())

    def _fetchone(self, query: str, params: tuple[object, ...]) -> tuple | None:
        connection = self._connect()
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def _version_sort_key(self, record: VersionRecord):
        try:
            from packaging.version import InvalidVersion, Version
        except ImportError:  # pragma: no cover - fallback for minimal pip environments
            from pip._vendor.packaging.version import InvalidVersion, Version

        try:
            return (1, Version(record.version))
        except InvalidVersion:
            return (0, record.version)
