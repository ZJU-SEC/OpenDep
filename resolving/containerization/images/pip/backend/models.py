from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class VersionRecord:
    name: str
    version: str
    yanked: bool = False
    source_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "yanked": self.yanked,
            "source_kind": self.source_kind,
        }


@dataclass(frozen=True, slots=True)
class PackageMetadataRecord:
    name: str
    version: str
    requires_dist: tuple[str, ...] = ()
    requires_python: str | None = None
    yanked: bool = False
    source_kind: str = "unknown"
    artifact_url: str | None = None
    artifact_hash: str | None = None
    extracted_at: str | None = None
    dependency_source_detail: str | None = None
    parse_warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "requires_dist": list(self.requires_dist),
            "requires_python": self.requires_python,
            "yanked": self.yanked,
            "source_kind": self.source_kind,
            "artifact_url": self.artifact_url,
            "artifact_hash": self.artifact_hash,
            "extracted_at": self.extracted_at,
            "dependency_source_detail": self.dependency_source_detail,
            "parse_warnings": list(self.parse_warnings),
        }
