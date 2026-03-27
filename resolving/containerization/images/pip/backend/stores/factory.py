from __future__ import annotations

from resolving.containerization.images.pip.backend.config import BackendConfig
from resolving.containerization.images.pip.backend.errors import BackendError
from resolving.containerization.images.pip.backend.stores.base import IndexStore
from resolving.containerization.images.pip.backend.stores.postgres import (
    PostgresIndexStore,
)


def build_index_store(config: BackendConfig) -> IndexStore:
    if not config.index_dsn:
        raise BackendError(
            "BACKEND_MISCONFIGURED",
            "indexed mode requires PIP_INDEX_DSN to be configured",
            retryable=False,
        )

    if config.index_backend and config.index_backend != "postgres":
        raise BackendError(
            "BACKEND_MISCONFIGURED",
            f"unsupported index backend: {config.index_backend}",
            retryable=False,
        )

    return PostgresIndexStore(config.index_dsn, table_name=config.index_table)
