from __future__ import annotations

from email.parser import BytesParser
from pathlib import Path
import tempfile

from pip_models import ExtractionJob, ExtractedMetadataRecord, utc_now_iso
from resolving.containerization.images.pip.backend.inspectors.archive import (
    infer_name_version_from_filename,
    open_distribution_archive,
)
from resolving.containerization.images.pip.backend.inspectors.setup_parsing import (
    parse_pyproject_text,
    parse_setup_cfg_text,
    parse_setup_py_file,
)


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _strip_inline_comment(value: str) -> str:
    if " #" in value:
        return value.split(" #", 1)[0].strip()
    return value.strip()


def _parse_section_header(header: str) -> tuple[str | None, str | None]:
    inner = header[1:-1].strip()
    if not inner:
        return None, None
    if ":" in inner:
        extra_name, marker = inner.split(":", 1)
        return extra_name.strip() or None, marker.strip() or None

    marker_hints = (" ", "<", ">", "=", "!", "~", "python_version", "sys_platform", "platform_", "os_name")
    if any(hint in inner for hint in marker_hints):
        return None, inner
    return inner, None


def _apply_markers(dependency: str, *, extra_name: str | None, marker: str | None) -> str | None:
    cleaned = _strip_inline_comment(dependency)
    if not cleaned:
        return None
    if cleaned.startswith(("-r ", "--requirement ", "-c ", "--constraint ", "--index-url ", "--extra-index-url ")):
        return None

    requirement, separator, existing_marker = cleaned.partition(";")
    markers: list[str] = []
    if separator and existing_marker.strip():
        markers.append(existing_marker.strip())
    if extra_name:
        markers.append(f"extra == '{extra_name}'")
    if marker:
        markers.append(marker)

    requirement = requirement.strip()
    if not requirement:
        return None
    if markers:
        return f"{requirement} ; {' and '.join(markers)}"
    return requirement


def _parse_requires_text(raw_text: str) -> tuple[str, ...]:
    dependencies: list[str] = []
    current_extra: str | None = None
    current_marker: str | None = None
    for raw_line in raw_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current_extra, current_marker = _parse_section_header(stripped)
            continue
        dependency = _apply_markers(stripped, extra_name=current_extra, marker=current_marker)
        if not dependency:
            continue
        dependencies.append(dependency)
    return _dedupe(dependencies)


def _find_egg_info_requires(entries: list[str]) -> str | None:
    candidates = [
        name
        for name in entries
        if Path(name).name == "requires.txt" and ("egg-info" in name.lower() or "egg-info" == Path(name).parent.name.lower())
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda value: (value.count("/"), value))[0]


def _find_metadata_file(entries: list[str]) -> str | None:
    candidates = [name for name in entries if Path(name).name in {"PKG-INFO", "METADATA"}]
    if not candidates:
        return None
    return sorted(candidates, key=lambda value: (value.count("/"), value))[0]


def _find_archive_config(entries: list[str], basename: str) -> str | None:
    candidates = [name for name in entries if Path(name).name == basename]
    if not candidates:
        return None
    return sorted(candidates, key=lambda value: (value.count("/"), value))[0]


def _find_requirements_file(entries: list[str]) -> str | None:
    candidates = [
        name
        for name in entries
        if Path(name).name.startswith("requirements") and Path(name).suffix in {".txt", ".in"}
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda value: (value.count("/"), value))[0]


def _parse_metadata_text(raw_bytes: bytes) -> tuple[str, ...]:
    message = BytesParser().parsebytes(raw_bytes)
    requires_dist = [value.strip() for value in message.get_all("Requires-Dist") or () if value and value.strip()]
    if requires_dist:
        return _dedupe(requires_dist)

    requires = [value.strip() for value in message.get_all("Requires") or () if value and value.strip()]
    normalized: list[str] = []
    for value in requires:
        normalized.extend(item.strip() for item in value.split(",") if item.strip())
    return _dedupe(normalized)


def _parse_setup_py_from_archive(archive, file_name: str) -> tuple[str, ...]:
    with tempfile.TemporaryDirectory() as temp_dir:
        temporary_path = Path(temp_dir, "setup.py")
        temporary_path.write_bytes(archive.read_bytes(file_name))
        return _dedupe(parse_setup_py_file(str(temporary_path)))


class LegacyFallbackExtractor:
    def extract(self, job: ExtractionJob, *, primary_error: Exception | None = None) -> ExtractedMetadataRecord:
        inferred_name, inferred_version = infer_name_version_from_filename(job.filename)
        fallback_warning = None
        if primary_error is not None:
            fallback_warning = (
                f"resolver inspector failed for `{job.filename}` with {primary_error.__class__.__name__}; "
                "legacy fallback extraction was used"
            )

        with open_distribution_archive(job.artifact_path) as archive:
            source_kind: str | None = None
            dependency_source_detail: str | None = None
            requires_dist: tuple[str, ...] = ()

            requires_name = _find_egg_info_requires(archive.names)
            if requires_name is not None:
                requires_dist = _parse_requires_text(archive.read_text(requires_name))
                source_kind = "legacy-egg-info-requires"
                dependency_source_detail = requires_name

            if not requires_dist:
                metadata_name = _find_metadata_file(archive.names)
                if metadata_name is not None:
                    requires_dist = _parse_metadata_text(archive.read_bytes(metadata_name))
                    if requires_dist:
                        source_kind = "legacy-pkg-info"
                        dependency_source_detail = metadata_name

            if not requires_dist:
                setup_cfg_name = _find_archive_config(archive.names, "setup.cfg")
                if setup_cfg_name is not None:
                    requires_dist = _dedupe(parse_setup_cfg_text(archive.read_text(setup_cfg_name)))
                    if requires_dist:
                        source_kind = "legacy-setup.cfg"
                        dependency_source_detail = setup_cfg_name

            if not requires_dist:
                pyproject_name = _find_archive_config(archive.names, "pyproject.toml")
                if pyproject_name is not None:
                    requires_dist = _dedupe(parse_pyproject_text(archive.read_text(pyproject_name)))
                    if requires_dist:
                        source_kind = "legacy-pyproject.toml"
                        dependency_source_detail = pyproject_name

            if not requires_dist:
                setup_py_name = _find_archive_config(archive.names, "setup.py")
                if setup_py_name is not None:
                    requires_dist = _parse_setup_py_from_archive(archive, setup_py_name)
                    if requires_dist:
                        source_kind = "legacy-setup.py"
                        dependency_source_detail = setup_py_name

            if not requires_dist:
                requirements_name = _find_requirements_file(archive.names)
                if requirements_name is not None:
                    requires_dist = _parse_requires_text(archive.read_text(requirements_name))
                    if requires_dist:
                        source_kind = "legacy-requirements-txt"
                        dependency_source_detail = requirements_name

            if not requires_dist or source_kind is None or dependency_source_detail is None:
                raise ValueError(
                    f"legacy fallback could not find requirements metadata inside {job.artifact_path}"
                )

            warnings: list[str] = []
            if fallback_warning:
                warnings.append(fallback_warning)

            return ExtractedMetadataRecord(
                name=job.project_name or inferred_name or "unknown",
                version=job.version or inferred_version or "unknown",
                requires_dist=requires_dist,
                requires_python=None,
                yanked=False,
                source_kind=source_kind,
                artifact_path=job.artifact_path,
                artifact_kind=job.artifact_kind,
                artifact_filename=job.filename,
                dependency_source_detail=dependency_source_detail,
                parse_warnings=tuple(warnings),
                extracted_at=utc_now_iso(),
                extraction_backend="legacy-fallback",
            )
