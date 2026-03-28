from __future__ import annotations

from dataclasses import dataclass


_DYNAMIC_VERSION_TOKENS = {
    "LATEST": "latest",
    "RELEASE": "release",
}


def _looks_like_version_range(version: str) -> bool:
    return (
        len(version) >= 2
        and version[0] in {"[", "("}
        and version[-1] in {"]", ")"}
    )


@dataclass(frozen=True, slots=True)
class VersionMetadataPlan:
    version_spec: str
    strategy: str
    required: bool
    supported: bool
    direct_pom_fetch: bool
    reason: str


def build_version_metadata_plan(
    version_spec: str,
    *,
    include_version_metadata: bool = True,
) -> VersionMetadataPlan:
    normalized = version_spec.strip()
    if not normalized:
        raise ValueError("version_spec cannot be empty")

    if not include_version_metadata:
        return VersionMetadataPlan(
            version_spec=normalized,
            strategy="disabled",
            required=False,
            supported=True,
            direct_pom_fetch=True,
            reason="version metadata warming disabled by request",
        )

    upper_version = normalized.upper()
    if upper_version.endswith("SNAPSHOT"):
        return VersionMetadataPlan(
            version_spec=normalized,
            strategy="snapshot",
            required=True,
            supported=False,
            direct_pom_fetch=False,
            reason="snapshot metadata warming is out of scope for the current Maven preprocess phase",
        )

    if upper_version in _DYNAMIC_VERSION_TOKENS:
        return VersionMetadataPlan(
            version_spec=normalized,
            strategy=_DYNAMIC_VERSION_TOKENS[upper_version],
            required=True,
            supported=True,
            direct_pom_fetch=False,
            reason="dynamic Maven versions require repository metadata before a concrete version can be selected",
        )

    if _looks_like_version_range(normalized):
        return VersionMetadataPlan(
            version_spec=normalized,
            strategy="range",
            required=True,
            supported=True,
            direct_pom_fetch=False,
            reason="Maven version ranges require repository metadata and still cannot be fully warmed without resolving a concrete version",
        )

    return VersionMetadataPlan(
        version_spec=normalized,
        strategy="none",
        required=False,
        supported=True,
        direct_pom_fetch=True,
        reason="fixed Maven versions do not require metadata warming",
    )


__all__ = [
    "VersionMetadataPlan",
    "build_version_metadata_plan",
]
