from __future__ import annotations

from email.parser import BytesParser
from pathlib import Path
import tempfile

from resolving.containerization.images.pip.backend.inspectors.archive import (
    infer_name_version_from_filename,
    open_distribution_archive,
)
from resolving.containerization.images.pip.backend.inspectors.base import DependencyInspector
from resolving.containerization.images.pip.backend.inspectors.setup_parsing import (
    parse_pyproject_text,
    parse_setup_cfg_text,
    parse_setup_py_file,
)
from resolving.containerization.images.pip.backend.models import PackageMetadataRecord


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


class SdistDependencyInspector(DependencyInspector):
    def inspect_distribution(
        self,
        artifact_path: str,
        *,
        project_name: str | None = None,
        version: str | None = None,
    ) -> PackageMetadataRecord:
        inferred_name, inferred_version = infer_name_version_from_filename(artifact_path)
        with open_distribution_archive(artifact_path) as archive:
            metadata_record = self._inspect_metadata_files(
                archive,
                project_name=project_name or inferred_name,
                version=version or inferred_version,
            )
            if metadata_record is not None:
                return metadata_record

            config_record = self._inspect_config_files(
                archive,
                project_name=project_name or inferred_name,
                version=version or inferred_version,
            )
            if config_record is not None:
                return config_record

        raise ValueError(f"unable to derive dependency metadata from sdist: {artifact_path}")

    def _inspect_metadata_files(
        self,
        archive,
        *,
        project_name: str | None,
        version: str | None,
    ) -> PackageMetadataRecord | None:
        metadata_name = archive.find_first(basename="PKG-INFO")
        if metadata_name is None:
            return None

        message = BytesParser().parsebytes(archive.read_bytes(metadata_name))
        requires_dist = tuple(message.get_all("Requires-Dist") or ())
        if not requires_dist:
            return None

        return PackageMetadataRecord(
            name=message.get("Name") or project_name or "unknown",
            version=message.get("Version") or version or "unknown",
            requires_dist=requires_dist,
            requires_python=message.get("Requires-Python"),
            yanked=False,
            source_kind="sdist-pkg-info",
            dependency_source_detail=metadata_name,
            parse_warnings=(),
        )

    def _inspect_config_files(
        self,
        archive,
        *,
        project_name: str | None,
        version: str | None,
    ) -> PackageMetadataRecord | None:
        parsers = (
            ("setup.cfg", "sdist-setup.cfg", self._parse_setup_cfg_from_archive),
            ("pyproject.toml", "sdist-pyproject.toml", self._parse_pyproject_from_archive),
            ("setup.py", "sdist-setup.py", self._parse_setup_py_from_archive),
        )
        for basename, source_kind, parser in parsers:
            file_name = archive.find_first(basename=basename)
            if file_name is None:
                continue
            dependencies = parser(archive, file_name)
            if not dependencies:
                continue
            return PackageMetadataRecord(
                name=project_name or "unknown",
                version=version or "unknown",
                requires_dist=_dedupe(dependencies),
                requires_python=None,
                yanked=False,
                source_kind=source_kind,
                dependency_source_detail=file_name,
                parse_warnings=(),
            )
        return None

    def _parse_setup_cfg_from_archive(self, archive, file_name: str) -> list[str]:
        return parse_setup_cfg_text(archive.read_text(file_name))

    def _parse_pyproject_from_archive(self, archive, file_name: str) -> list[str]:
        return parse_pyproject_text(archive.read_text(file_name))

    def _parse_setup_py_from_archive(self, archive, file_name: str) -> list[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            temporary_path = Path(temp_dir, "setup.py")
            temporary_path.write_bytes(archive.read_bytes(file_name))
            return parse_setup_py_file(str(temporary_path))
