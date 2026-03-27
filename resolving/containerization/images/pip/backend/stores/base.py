from __future__ import annotations

from abc import ABC, abstractmethod

from resolving.containerization.images.pip.backend.models import PackageMetadataRecord, VersionRecord


class IndexStore(ABC):
    """Abstract storage interface for indexed package metadata."""

    @abstractmethod
    def list_versions(self, project_name: str) -> list[VersionRecord]:
        """Return indexed versions for a project."""

    @abstractmethod
    def get_release(self, project_name: str, version: str) -> PackageMetadataRecord | None:
        """Return indexed metadata for a specific release when available."""

    @abstractmethod
    def put_release(self, record: PackageMetadataRecord) -> None:
        """Insert or update a metadata record."""

    def close(self) -> None:
        """Release any underlying resources when needed."""

