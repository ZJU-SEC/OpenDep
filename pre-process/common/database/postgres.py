from __future__ import annotations

from contextlib import contextmanager
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
        raise RuntimeError("PostgreSQL access requires psycopg or psycopg2 to be installed") from exc


@dataclass(frozen=True, slots=True)
class PostgresSettings:
    host: str = "127.0.0.1"
    port: int = 55432
    database: str = "opendep_preprocess"
    user: str = "opendep"
    password: str = "opendep"

    @classmethod
    def from_env(cls) -> "PostgresSettings":
        return cls(
            host=os.getenv("PREPROCESS_DB_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=int((os.getenv("PREPROCESS_DB_PORT", "55432").strip() or "55432")),
            database=os.getenv("PREPROCESS_DB_NAME", "opendep_preprocess").strip() or "opendep_preprocess",
            user=os.getenv("PREPROCESS_DB_USER", "opendep").strip() or "opendep",
            password=os.getenv("PREPROCESS_DB_PASSWORD", "opendep"),
        )

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


def resolve_dsn(explicit_dsn: str | None = None) -> str:
    if explicit_dsn:
        return explicit_dsn
    env_dsn = os.getenv("PREPROCESS_DB_DSN")
    if env_dsn:
        return env_dsn
    return PostgresSettings.from_env().dsn


def connect_postgres(
    dsn: str | None = None,
    *,
    driver: Any | None = None,
):
    resolved_dsn = resolve_dsn(dsn)
    if driver is None:
        _, driver = _load_driver()
    return driver.connect(resolved_dsn)


@contextmanager
def postgres_transaction(connection):
    try:
        yield connection
    except Exception:
        rollback = getattr(connection, "rollback", None)
        if callable(rollback):
            rollback()
        raise
    else:
        connection.commit()


@contextmanager
def postgres_cursor(connection):
    with connection.cursor() as cursor:
        yield cursor


def execute_sql_text(connection, sql_text: str) -> None:
    with postgres_transaction(connection):
        with postgres_cursor(connection) as cursor:
            cursor.execute(sql_text)


def execute_sql_file(connection, sql_file: str | Path) -> None:
    sql_path = Path(sql_file)
    execute_sql_text(connection, sql_path.read_text(encoding="utf-8"))
