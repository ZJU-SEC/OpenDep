from __future__ import annotations

import collections
import math

try:
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.utils import canonicalize_name
    from packaging.version import InvalidVersion, Version
except ImportError:  # pragma: no cover - fallback for minimal pip environments
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.specifiers import SpecifierSet
    from pip._vendor.packaging.utils import canonicalize_name
    from pip._vendor.packaging.version import InvalidVersion, Version

from Resolver.containerization.images.pip.backend.metadata_sources.base import MetadataSource
from Resolver.containerization.images.pip.backend.models import PackageMetadataRecord, VersionRecord
from Resolver.containerization.images.pip.backend.resolver_core.candidates import Candidate
from Resolver.containerization.images.pip.backend.resolver_core.extras_provider import ExtrasProvider
from Resolver.containerization.images.pip.backend.resolver_core.requirements import (
    identifier_for_requirement,
)


def _is_prerelease(version: str) -> bool:
    try:
        return Version(version).is_prerelease
    except InvalidVersion:
        return False


def _sort_key(candidate: Candidate) -> tuple[int, object]:
    try:
        return (1, Version(candidate.version))
    except InvalidVersion:
        return (0, candidate.version)


class PipProvider(ExtrasProvider):
    def __init__(self, metadata_source: MetadataSource, user_requested: dict[str, int]) -> None:
        self._metadata_source = metadata_source
        self._user_requested = user_requested
        self._known_depths = collections.defaultdict(lambda: math.inf)

    def identify(self, requirement_or_candidate):
        if isinstance(requirement_or_candidate, Requirement):
            return identifier_for_requirement(requirement_or_candidate)
        if getattr(requirement_or_candidate, "extras", ()):
            formatted_extras = ",".join(sorted(set(requirement_or_candidate.extras)))
            return f"{canonicalize_name(requirement_or_candidate.name)}[{formatted_extras}]"
        return canonicalize_name(requirement_or_candidate.name)

    def get_extras_for(self, requirement_or_candidate):
        return tuple(sorted(getattr(requirement_or_candidate, "extras", ())))

    def get_base_requirement(self, candidate: Candidate):
        return Requirement(f"{candidate.name}=={candidate.version}")

    def get_preference(self, identifier, resolutions, candidates, information, backtrack_causes):
        criterion = list(information[identifier])
        _, ireqs = (None, [item.requirement for item in criterion])
        operators = [
            specifier.operator
            for specifier_set in (ireq.specifier for ireq in ireqs if ireq)
            for specifier in specifier_set
        ]

        direct = False
        pinned = any(operator[:2] == "==" for operator in operators)
        unfree = bool(operators)

        try:
            requested_order = self._user_requested[identifier]
        except KeyError:
            requested_order = math.inf
            parent_depths = (
                self._known_depths[parent.name] if parent is not None else 0.0
                for _, parent in information[identifier]
            )
            inferred_depth = min(parent_depths, default=0.0) + 1.0
        else:
            inferred_depth = 1.0

        self._known_depths[identifier] = inferred_depth
        delay_this = identifier == "setuptools"

        return (
            delay_this,
            not direct,
            not pinned,
            inferred_depth,
            requested_order,
            not unfree,
            identifier,
        )

    def find_matches(self, identifier, requirements, incompatibilities):
        requirement_set = set(requirements[identifier])
        extras = tuple(
            sorted(
                {
                    extra
                    for requirement in requirement_set
                    for extra in requirement.extras
                }
            )
        )

        project_name = canonicalize_name(next(iter(requirement_set)).name)
        bad_versions = {candidate.version for candidate in incompatibilities[identifier]}
        available_versions = [
            version_record
            for version_record in self._metadata_source.list_versions(project_name)
            if version_record.version not in bad_versions
        ]
        matching_versions = self._filter_matching_versions(available_versions, requirement_set)

        candidates: list[Candidate] = []
        for version_record in matching_versions:
            metadata = self._load_metadata(project_name, version_record)
            if metadata is None:
                continue
            candidates.append(Candidate(metadata, extras=extras))

        allowed_candidates = []
        for candidate in candidates:
            if candidate.yanked and not self._has_explicit_pin(requirement_set):
                continue
            allowed_candidates.append(candidate)
        return sorted(allowed_candidates, key=_sort_key, reverse=True)

    def is_satisfied_by(self, requirement, candidate):
        if canonicalize_name(requirement.name) != canonicalize_name(candidate.name):
            return False
        return requirement.specifier.contains(candidate.version, prereleases=True)

    def get_dependencies(self, candidate):
        return candidate.dependencies

    def _filter_matching_versions(
        self,
        versions: list[VersionRecord],
        requirements: set[Requirement],
    ) -> list[VersionRecord]:
        candidates = list(versions)
        for requirement in requirements:
            if requirement.specifier == SpecifierSet(""):
                non_prereleases = [
                    version_record
                    for version_record in candidates
                    if not _is_prerelease(version_record.version)
                ]
                if non_prereleases:
                    candidates = non_prereleases
                continue

            prereleases = any(
                spec.prereleases is True
                for spec in requirement.specifier
            )
            candidates = [
                version_record
                for version_record in candidates
                if requirement.specifier.contains(
                    version_record.version,
                    prereleases=prereleases,
                )
            ]
        return candidates

    def _load_metadata(
        self,
        project_name: str,
        version_record: VersionRecord,
    ) -> PackageMetadataRecord | None:
        metadata = self._metadata_source.get_release(project_name, version_record.version)
        if metadata is not None:
            return metadata
        try:
            return self._metadata_source.warm(project_name, version_record.version)
        except Exception:
            return None

    def _has_explicit_pin(self, requirements: set[Requirement]) -> bool:
        for requirement in requirements:
            for specifier in requirement.specifier:
                if specifier.operator == "==":
                    return True
        return False
