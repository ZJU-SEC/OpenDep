"""Storage abstractions for indexed pip metadata."""

from resolving.containerization.images.pip.backend.stores.base import IndexStore
from resolving.containerization.images.pip.backend.stores.factory import build_index_store
from resolving.containerization.images.pip.backend.stores.postgres import (
    PostgresIndexStore,
)

__all__ = ["IndexStore", "PostgresIndexStore", "build_index_store"]
