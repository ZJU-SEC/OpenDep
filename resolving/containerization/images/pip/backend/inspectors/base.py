from __future__ import annotations

from abc import ABC, abstractmethod

from resolving.containerization.images.pip.backend.models import PackageMetadataRecord


class DependencyInspector(ABC):
    """Abstract inspector for deriving dependency metadata from distributions."""

    @abstractmethod
    def inspect_distribution(
        self,
        artifact_path: str,
        *,
        project_name: str | None = None,
        version: str | None = None,
    ) -> PackageMetadataRecord:
        """Inspect a local distribution artifact and return normalized metadata."""
