from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class GoModuleSpec:
    module_path: str
    version: str

    @property
    def identity(self) -> str:
        return f"{self.module_path}@{self.version}"

    def to_dict(self) -> dict[str, str]:
        return {
            "module_path": self.module_path,
            "version": self.version,
        }


def parse_module_spec(spec_text: str) -> GoModuleSpec:
    normalized = spec_text.strip()
    if not normalized:
        raise ValueError("module spec is required")

    module_path, sep, version = normalized.rpartition("@")
    if not sep:
        raise ValueError(f"invalid module spec `{spec_text}`; expected `module@version`")
    module_path = module_path.strip()
    version = version.strip()
    if not module_path:
        raise ValueError(f"invalid module spec `{spec_text}`; module path is empty")
    if not version:
        raise ValueError(f"invalid module spec `{spec_text}`; version is empty")
    return GoModuleSpec(module_path=module_path, version=version)


def load_module_specs(
    *,
    specs: Sequence[str] | None = None,
    module_file: str | Path | None = None,
) -> list[GoModuleSpec]:
    raw_specs: list[str] = []
    if specs:
        raw_specs.extend(specs)
    if module_file:
        raw_specs.extend(_read_module_file(module_file))

    ordered: dict[tuple[str, str], GoModuleSpec] = {}
    for raw_spec in raw_specs:
        parsed = parse_module_spec(raw_spec)
        ordered[(parsed.module_path, parsed.version)] = parsed
    return list(ordered.values())


def _read_module_file(module_file: str | Path) -> Iterable[str]:
    path = Path(module_file)
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        yield stripped
