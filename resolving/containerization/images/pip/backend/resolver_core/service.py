from __future__ import annotations

from dataclasses import dataclass

try:
    from packaging.requirements import Requirement
except ImportError:  # pragma: no cover - fallback for minimal pip environments
    from pip._vendor.packaging.requirements import Requirement

try:
    from resolvelib import BaseReporter, resolving
except ImportError:  # pragma: no cover - fallback for minimal pip environments
    from pip._vendor.resolvelib import BaseReporter, Resolver

from resolving.containerization.images.pip.backend.metadata_sources.base import MetadataSource
from resolving.containerization.images.pip.backend.resolver_core.provider import PipProvider
from resolving.containerization.images.pip.backend.resolver_core.requirements import (
    identifier_for_requirement,
    parse_requirement_strings,
)


@dataclass(slots=True)
class ResolverCore:
    metadata_source: MetadataSource
    reporter: BaseReporter | None = None

    def resolve(self, requirements: list[str], *, max_rounds: int = 2000):
        parsed_requirements = parse_requirement_strings(requirements)
        return self.resolve_requirements(parsed_requirements, max_rounds=max_rounds)

    def resolve_requirements(
        self,
        requirements: list[Requirement],
        *,
        max_rounds: int = 2000,
    ):
        user_requested = {
            identifier_for_requirement(requirement): index
            for index, requirement in enumerate(requirements)
        }
        provider = PipProvider(self.metadata_source, user_requested)
        reporter = self.reporter or BaseReporter()
        resolver = Resolver(provider, reporter)
        return resolver.resolve(requirements, max_rounds=max_rounds)
