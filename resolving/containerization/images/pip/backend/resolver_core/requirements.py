from __future__ import annotations

import sys
from typing import Iterable

try:
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.utils import canonicalize_name
except ImportError:  # pragma: no cover - fallback for minimal pip environments
    from pip._vendor.packaging.requirements import InvalidRequirement, Requirement
    from pip._vendor.packaging.utils import canonicalize_name


NO_EXTRA_SENTINEL = "__opendep_no_extra__"
PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}"


def normalize_requirement_line(raw_requirement: str) -> str | None:
    cleaned = raw_requirement.strip()
    if not cleaned or cleaned.startswith("#"):
        return None
    if "#" in cleaned:
        cleaned = cleaned.split("#", 1)[0].strip()
    return cleaned or None


def identifier_for_requirement(requirement: Requirement) -> str:
    base_name = canonicalize_name(requirement.name)
    if requirement.extras:
        formatted_extras = ",".join(sorted(set(requirement.extras)))
        return f"{base_name}[{formatted_extras}]"
    return base_name


def parse_requirement_strings(requirement_strings: Iterable[str]) -> list[Requirement]:
    parsed_requirements: list[Requirement] = []
    for raw_requirement in requirement_strings:
        normalized = normalize_requirement_line(raw_requirement)
        if normalized is None:
            continue
        try:
            requirement = Requirement(normalized)
        except InvalidRequirement:
            continue
        if requirement.marker is not None and not requirement.marker.evaluate(
            {
                "extra": NO_EXTRA_SENTINEL,
                "python_version": PYTHON_VERSION,
            }
        ):
            continue
        parsed_requirements.append(requirement)
    return parsed_requirements
