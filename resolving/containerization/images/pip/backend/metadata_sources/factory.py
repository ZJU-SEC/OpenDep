from __future__ import annotations

from resolving.containerization.images.pip.backend.config import BackendConfig
from resolving.containerization.images.pip.backend.errors import BackendError
from resolving.containerization.images.pip.backend.metadata_sources.base import MetadataSource
from resolving.containerization.images.pip.backend.metadata_sources.indexed import (
    IndexedMetadataSource,
)
from resolving.containerization.images.pip.backend.metadata_sources.live import LiveMetadataSource
from resolving.containerization.images.pip.backend.stores.factory import build_index_store


def build_metadata_source(config: BackendConfig, *, mode_override: str | None = None) -> MetadataSource:
    mode = (mode_override or config.metadata_mode).strip().lower()
    if mode == "live":
        return LiveMetadataSource(
            cache_dir=config.cache_dir,
            pypi_json_base_url=config.pypi_json_base_url,
            http_user_agent=config.http_user_agent,
        )

    if mode != "indexed":
        raise BackendError(
            "INVALID_ARGUMENT",
            f"unsupported metadata mode: {mode}",
            retryable=False,
        )

    fallback_source = None
    if config.index_fallback_to_live:
        fallback_source = LiveMetadataSource(
            cache_dir=config.cache_dir,
            pypi_json_base_url=config.pypi_json_base_url,
            http_user_agent=config.http_user_agent,
        )
    store = build_index_store(config)
    return IndexedMetadataSource(store, fallback_source=fallback_source)
