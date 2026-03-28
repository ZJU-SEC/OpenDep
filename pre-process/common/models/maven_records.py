from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _normalize_part(value: str, *, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty")
    if any(char.isspace() for char in normalized):
        raise ValueError(f"{label} cannot contain whitespace: {value!r}")
    return normalized


@dataclass(frozen=True, slots=True)
class MavenCoordinate:
    group_id: str
    artifact_id: str
    version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "group_id", _normalize_part(self.group_id, label="group_id"))
        object.__setattr__(self, "artifact_id", _normalize_part(self.artifact_id, label="artifact_id"))
        object.__setattr__(self, "version", _normalize_part(self.version, label="version"))

    @classmethod
    def from_string(cls, raw_value: str) -> "MavenCoordinate":
        value = raw_value.strip()
        if not value:
            raise ValueError("Maven coordinate cannot be empty")
        parts = value.split(":")
        if len(parts) != 3:
            raise ValueError(f"invalid Maven coordinate `{raw_value}`; expected `groupId:artifactId:version`")
        return cls(parts[0], parts[1], parts[2])

    @property
    def ga(self) -> str:
        return f"{self.group_id}:{self.artifact_id}"

    @property
    def gav(self) -> str:
        return f"{self.group_id}:{self.artifact_id}:{self.version}"

    @property
    def group_path(self) -> str:
        return self.group_id.replace(".", "/")

    @property
    def artifact_directory(self) -> str:
        return f"{self.group_path}/{self.artifact_id}/{self.version}"

    def artifact_filename(self, extension: str = "pom") -> str:
        normalized_extension = extension.strip().lstrip(".")
        if not normalized_extension:
            raise ValueError("extension cannot be empty")
        return f"{self.artifact_id}-{self.version}.{normalized_extension}"

    def to_dict(self) -> dict[str, str]:
        return {
            "group_id": self.group_id,
            "artifact_id": self.artifact_id,
            "version": self.version,
            "ga": self.ga,
            "gav": self.gav,
            "group_path": self.group_path,
            "artifact_directory": self.artifact_directory,
        }


@dataclass(frozen=True, slots=True)
class LocalRepositoryLayout:
    repository_root: str
    coordinate: MavenCoordinate

    def __post_init__(self) -> None:
        normalized_root = str(Path(self.repository_root).expanduser().resolve())
        if not normalized_root:
            raise ValueError("repository_root cannot be empty")
        object.__setattr__(self, "repository_root", normalized_root)

    @property
    def artifact_directory(self) -> str:
        return self.coordinate.artifact_directory

    @property
    def absolute_artifact_directory(self) -> str:
        return str(Path(self.repository_root, self.artifact_directory))

    @property
    def pom_filename(self) -> str:
        return self.coordinate.artifact_filename("pom")

    @property
    def pom_relative_path(self) -> str:
        return f"{self.artifact_directory}/{self.pom_filename}"

    @property
    def pom_path(self) -> str:
        return str(Path(self.repository_root, self.pom_relative_path))

    @property
    def metadata_filename(self) -> str:
        return "maven-metadata.xml"

    @property
    def metadata_relative_path(self) -> str:
        return f"{self.coordinate.group_path}/{self.coordinate.artifact_id}/{self.metadata_filename}"

    @property
    def metadata_path(self) -> str:
        return str(Path(self.repository_root, self.metadata_relative_path))

    @property
    def tracking_filename(self) -> str:
        return "_remote.repositories"

    @property
    def tracking_relative_path(self) -> str:
        return f"{self.artifact_directory}/{self.tracking_filename}"

    @property
    def tracking_path(self) -> str:
        return str(Path(self.repository_root, self.tracking_relative_path))

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_root": self.repository_root,
            "coordinate": self.coordinate.to_dict(),
            "artifact_directory": self.artifact_directory,
            "absolute_artifact_directory": self.absolute_artifact_directory,
            "pom_filename": self.pom_filename,
            "pom_relative_path": self.pom_relative_path,
            "pom_path": self.pom_path,
            "metadata_filename": self.metadata_filename,
            "metadata_relative_path": self.metadata_relative_path,
            "metadata_path": self.metadata_path,
            "tracking_filename": self.tracking_filename,
            "tracking_relative_path": self.tracking_relative_path,
            "tracking_path": self.tracking_path,
        }


@dataclass(frozen=True, slots=True)
class WarmRequest:
    coordinate: MavenCoordinate
    include_version_metadata: bool = True
    source_type: str = "explicit"
    source_path: str | None = None
    source_line: int | None = None

    def __post_init__(self) -> None:
        if self.source_line is not None and self.source_line <= 0:
            raise ValueError("source_line must be positive when provided")

    @property
    def request_key(self) -> str:
        return self.coordinate.gav

    def to_dict(self) -> dict[str, Any]:
        return {
            "coordinate": self.coordinate.to_dict(),
            "include_version_metadata": self.include_version_metadata,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "source_line": self.source_line,
            "request_key": self.request_key,
        }


__all__ = [
    "LocalRepositoryLayout",
    "MavenCoordinate",
    "WarmRequest",
]
