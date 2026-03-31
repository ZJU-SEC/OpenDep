from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class NpmPackageSpec:
    name: str

    @property
    def identity(self) -> str:
        return self.name

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
        }


def parse_package_spec(spec_text: str) -> NpmPackageSpec:
    normalized = spec_text.strip()
    if not normalized:
        raise ValueError("package spec is required")
    if any(char.isspace() for char in normalized):
        raise ValueError(f"invalid package spec `{spec_text}`; whitespace is not allowed")

    if normalized.startswith("@"):
        scope, separator, package = normalized.partition("/")
        if not separator or scope == "@" or not package:
            raise ValueError(f"invalid scoped package spec `{spec_text}`; expected `@scope/name`")
        if "/" in package:
            raise ValueError(f"invalid scoped package spec `{spec_text}`; expected exactly one `/`")
        if "@" in package:
            raise ValueError(f"invalid package spec `{spec_text}`; expected package name without version")
    else:
        if "/" in normalized:
            raise ValueError(f"invalid package spec `{spec_text}`; expected unscoped package name or `@scope/name`")
        if "@" in normalized:
            raise ValueError(f"invalid package spec `{spec_text}`; expected package name without version")

    return NpmPackageSpec(name=normalized)


def load_package_specs(
    *,
    specs: Sequence[str] | None = None,
    package_file: str | Path | None = None,
) -> list[NpmPackageSpec]:
    raw_specs: list[str] = []
    if specs:
        raw_specs.extend(specs)
    if package_file:
        raw_specs.extend(_read_package_file(package_file))

    ordered: dict[str, NpmPackageSpec] = {}
    for raw_spec in raw_specs:
        parsed = parse_package_spec(raw_spec)
        ordered[parsed.name] = parsed
    return list(ordered.values())


def _read_package_file(package_file: str | Path) -> Iterable[str]:
    path = Path(package_file)
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        yield stripped
