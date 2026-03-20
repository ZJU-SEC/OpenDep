from __future__ import annotations

from email.parser import BytesParser

from Resolver.containerization.images.pip.backend.inspectors.archive import (
    infer_name_version_from_filename,
    open_distribution_archive,
)
from Resolver.containerization.images.pip.backend.inspectors.base import DependencyInspector
from Resolver.containerization.images.pip.backend.models import PackageMetadataRecord


class WheelDependencyInspector(DependencyInspector):
    def inspect_distribution(
        self,
        artifact_path: str,
        *,
        project_name: str | None = None,
        version: str | None = None,
    ) -> PackageMetadataRecord:
        inferred_name, inferred_version = infer_name_version_from_filename(artifact_path)
        with open_distribution_archive(artifact_path) as archive:
            metadata_name = archive.find_first(suffix=".dist-info/METADATA")
            if metadata_name is None:
                raise ValueError(f"wheel metadata file not found in {artifact_path}")

            message = BytesParser().parsebytes(archive.read_bytes(metadata_name))
            resolved_name = message.get("Name") or project_name or inferred_name or "unknown"
            resolved_version = message.get("Version") or version or inferred_version or "unknown"
            requires_dist = tuple(message.get_all("Requires-Dist") or ())
            requires_python = message.get("Requires-Python")

            warnings: list[str] = []
            if message.get("Name") is None:
                warnings.append("wheel metadata did not declare Name; fallback value was used")
            if message.get("Version") is None:
                warnings.append("wheel metadata did not declare Version; fallback value was used")

            return PackageMetadataRecord(
                name=resolved_name,
                version=resolved_version,
                requires_dist=requires_dist,
                requires_python=requires_python,
                yanked=False,
                source_kind="wheel-metadata",
                dependency_source_detail=metadata_name,
                parse_warnings=tuple(warnings),
            )
