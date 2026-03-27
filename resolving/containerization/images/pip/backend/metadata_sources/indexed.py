from __future__ import annotations

from resolving.containerization.images.pip.backend.metadata_sources.base import MetadataSource
from resolving.containerization.images.pip.backend.models import PackageMetadataRecord, VersionRecord
from resolving.containerization.images.pip.backend.stores.base import IndexStore


class IndexedMetadataSource(MetadataSource):
    mode_name = "indexed"

    def __init__(
        self,
        store: IndexStore,
        *,
        fallback_source: MetadataSource | None = None,
    ) -> None:
        self._store = store
        self._fallback_source = fallback_source

    def list_versions(self, project_name: str) -> list[VersionRecord]:
        versions = self._store.list_versions(project_name)
        if versions or self._fallback_source is None:
            return versions
        return self._fallback_source.list_versions(project_name)

    def get_release(self, project_name: str, version: str) -> PackageMetadataRecord | None:
        record = self._store.get_release(project_name, version)
        if record is not None or self._fallback_source is None:
            return record
        return self._fallback_source.get_release(project_name, version)

    def warm(self, project_name: str, version: str) -> PackageMetadataRecord:
        cached = self._store.get_release(project_name, version)
        if cached is not None:
            return cached
        if self._fallback_source is None:
            raise KeyError((project_name, version))
        warmed = self._fallback_source.warm(project_name, version)
        self._store.put_release(warmed)
        return warmed

    def close(self) -> None:
        self._store.close()
        if self._fallback_source is not None:
            self._fallback_source.close()
