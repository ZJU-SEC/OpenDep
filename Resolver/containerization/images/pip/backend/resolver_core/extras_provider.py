from __future__ import annotations

try:
    from resolvelib.providers import AbstractProvider
except ImportError:  # pragma: no cover - fallback for minimal pip environments
    from pip._vendor.resolvelib.providers import AbstractProvider


class ExtrasProvider(AbstractProvider):
    """Provider helper that constrains extras to the same base version."""

    def get_extras_for(self, requirement_or_candidate):
        raise NotImplementedError

    def get_base_requirement(self, candidate):
        raise NotImplementedError

    def identify(self, requirement_or_candidate):
        base = super().identify(requirement_or_candidate)
        extras = self.get_extras_for(requirement_or_candidate)
        if extras:
            return (base, extras)
        return base

    def get_dependencies(self, candidate):
        dependencies = super().get_dependencies(candidate)
        if candidate.extras:
            dependencies.append(self.get_base_requirement(candidate))
        return dependencies
