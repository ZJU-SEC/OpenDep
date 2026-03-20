from __future__ import annotations

try:
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.utils import canonicalize_name
except ImportError:  # pragma: no cover - fallback for minimal pip environments
    from pip._vendor.packaging.requirements import InvalidRequirement, Requirement
    from pip._vendor.packaging.utils import canonicalize_name

from Resolver.containerization.images.pip.backend.models import PackageMetadataRecord
from Resolver.containerization.images.pip.backend.resolver_core.requirements import (
    NO_EXTRA_SENTINEL,
    PYTHON_VERSION,
)


class Candidate:
    def __init__(
        self,
        metadata: PackageMetadataRecord,
        *,
        extras: tuple[str, ...] = (),
    ) -> None:
        self.name = canonicalize_name(metadata.name)
        self.version = metadata.version
        self.extras = tuple(sorted(set(extras)))
        self.requires_dist = tuple(metadata.requires_dist)
        self.requires_python = metadata.requires_python
        self.yanked = metadata.yanked
        self.source_kind = metadata.source_kind
        self._dependencies: list[Requirement] = []
        self._parsed_dependencies = False

    def __repr__(self) -> str:
        if not self.extras:
            return f"<{self.name}=={self.version}>"
        return f"<{self.name}[{','.join(self.extras)}]=={self.version}>"

    @property
    def dependencies(self) -> list[Requirement]:
        if self._parsed_dependencies:
            return self._dependencies

        extras_to_check = self.extras or (NO_EXTRA_SENTINEL,)
        for dependency_text in self.requires_dist:
            try:
                requirement = Requirement(dependency_text)
            except InvalidRequirement:
                continue

            if requirement.marker is None:
                self._dependencies.append(requirement)
                continue

            for extra in extras_to_check:
                if requirement.marker.evaluate(
                    {
                        "extra": extra,
                        "python_version": PYTHON_VERSION,
                    }
                ):
                    self._dependencies.append(requirement)
                    break

        self._parsed_dependencies = True
        return self._dependencies
