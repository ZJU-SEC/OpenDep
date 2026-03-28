from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
MAVEN_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]

for path in (MAVEN_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _normalize_part(value: str, *, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty")
    if any(char.isspace() for char in normalized):
        raise ValueError(f"{label} cannot contain whitespace: {value!r}")
    return normalized


@dataclass(frozen=True, slots=True)
class MavenPackageSpec:
    group_id: str
    artifact_id: str
    source_type: str = "explicit-package"
    source_path: str | None = None
    source_line: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "group_id", _normalize_part(self.group_id, label="group_id"))
        object.__setattr__(self, "artifact_id", _normalize_part(self.artifact_id, label="artifact_id"))
        if self.source_line is not None and self.source_line <= 0:
            raise ValueError("source_line must be positive when provided")

    @classmethod
    def from_string(
        cls,
        raw_value: str,
        *,
        source_type: str = "explicit-package",
        source_path: str | None = None,
        source_line: int | None = None,
    ) -> "MavenPackageSpec":
        value = raw_value.strip()
        if not value:
            raise ValueError("Maven package name cannot be empty")

        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError(
                f"invalid Maven package name `{raw_value}`; expected `groupId:artifactId`"
            )

        return cls(
            group_id=parts[0],
            artifact_id=parts[1],
            source_type=source_type,
            source_path=source_path,
            source_line=source_line,
        )

    @property
    def ga(self) -> str:
        return f"{self.group_id}:{self.artifact_id}"


class PackageListAdapter:
    def load(
        self,
        package_file: str,
        *,
        source_type: str = "package-file",
    ) -> list[MavenPackageSpec]:
        path = Path(package_file).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"package file does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"package file is not a file: {path}")

        packages: list[MavenPackageSpec] = []
        seen: set[str] = set()
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("--"):
                raise ValueError(f"invalid Maven package name in file at line {line_number}: {stripped}")

            package = MavenPackageSpec.from_string(
                stripped,
                source_type=source_type,
                source_path=str(path),
                source_line=line_number,
            )
            if package.ga in seen:
                continue
            seen.add(package.ga)
            packages.append(package)

        if not packages:
            raise ValueError(f"package file does not contain any Maven package names: {path}")
        return packages


def build_package_specs(
    raw_values,
    *,
    source_type: str = "explicit-package",
) -> list[MavenPackageSpec]:
    packages: list[MavenPackageSpec] = []
    seen: set[str] = set()
    for raw_value in raw_values or ():
        normalized = str(raw_value).strip()
        if not normalized:
            continue
        package = MavenPackageSpec.from_string(normalized, source_type=source_type)
        if package.ga in seen:
            continue
        seen.add(package.ga)
        packages.append(package)
    return packages


__all__ = [
    "MavenPackageSpec",
    "PackageListAdapter",
    "build_package_specs",
]
