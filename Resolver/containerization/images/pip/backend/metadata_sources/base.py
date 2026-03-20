from __future__ import annotations

from abc import ABC, abstractmethod

from Resolver.containerization.images.pip.backend.models import PackageMetadataRecord, VersionRecord


class MetadataSource(ABC):
    """Abstract metadata source used by the resolver core."""

    mode_name = "unknown"

    @abstractmethod
    def list_versions(self, project_name: str) -> list[VersionRecord]:
        """Return available versions for a project."""

    @abstractmethod
    def get_release(self, project_name: str, version: str) -> PackageMetadataRecord | None:
        """Return cached metadata for a specific release when available."""

    @abstractmethod
    def warm(self, project_name: str, version: str) -> PackageMetadataRecord:
        """Load or compute metadata for a specific release."""

    def close(self) -> None:
        """Release any underlying resources when needed."""

