from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
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


@dataclass(frozen=True, slots=True)
class GoModuleRequest:
    module_path: str
    version: str | None = None

    @property
    def identity(self) -> str:
        if self.version:
            return f"{self.module_path}@{self.version}"
        return self.module_path

    def to_spec(self, version: str | None = None) -> GoModuleSpec:
        resolved_version = version if version is not None else self.version
        if not resolved_version:
            raise ValueError(f"module request `{self.identity}` does not include a version")
        return GoModuleSpec(module_path=self.module_path, version=resolved_version)


_VERSION_PREFIX_RE = re.compile(r"^[vV]\d")


def _split_module_request(spec_text: str) -> tuple[str, str | None]:
    normalized = spec_text.strip()
    if not normalized:
        raise ValueError("module spec is required")

    module_path, sep, suffix = normalized.rpartition("@")
    if not sep:
        return normalized, None

    module_path = module_path.strip()
    suffix = suffix.strip()
    if not module_path:
        raise ValueError(f"invalid module spec `{spec_text}`; module path is empty")
    if not suffix:
        raise ValueError(f"invalid module spec `{spec_text}`; version is empty")
    if _VERSION_PREFIX_RE.match(suffix):
        return module_path, suffix
    return normalized, None


def parse_module_request(spec_text: str) -> GoModuleRequest:
    module_path, version = _split_module_request(spec_text)
    return GoModuleRequest(module_path=module_path, version=version)


def parse_module_spec(spec_text: str) -> GoModuleSpec:
    request = parse_module_request(spec_text)
    if request.version is None:
        raise ValueError(f"invalid module spec `{spec_text}`; expected `module@version`")
    return request.to_spec()


def load_module_requests(
    *,
    specs: Sequence[str] | None = None,
    module_file: str | Path | None = None,
) -> list[GoModuleRequest]:
    raw_specs: list[str] = []
    if specs:
        raw_specs.extend(specs)
    if module_file:
        raw_specs.extend(_read_module_file(module_file))

    ordered: dict[tuple[str, str | None], GoModuleRequest] = {}
    for raw_spec in raw_specs:
        parsed = parse_module_request(raw_spec)
        ordered[(parsed.module_path, parsed.version)] = parsed
    return list(ordered.values())


def load_module_specs(
    *,
    specs: Sequence[str] | None = None,
    module_file: str | Path | None = None,
) -> list[GoModuleSpec]:
    ordered: dict[tuple[str, str], GoModuleSpec] = {}
    for parsed in load_module_requests(specs=specs, module_file=module_file):
        if parsed.version is None:
            raise ValueError(f"invalid module spec `{parsed.identity}`; expected `module@version`")
        concrete = parsed.to_spec()
        ordered[(concrete.module_path, concrete.version)] = concrete
    return list(ordered.values())


def _read_module_file(module_file: str | Path) -> Iterable[str]:
    path = Path(module_file)
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        yield stripped
