from __future__ import annotations

from typing import Any

from resolving.gateway.errors import UnsupportedEcosystemError


class ResolverRegistry:
    def __init__(self, config: dict[str, Any]) -> None:
        self._resolvers = {
            resolver["ecosystem"]: resolver for resolver in config.get("resolvers", [])
        }

    def get(self, ecosystem: str) -> dict[str, Any] | None:
        return self._resolvers.get(ecosystem)

    def require(self, ecosystem: str) -> dict[str, Any]:
        resolver = self.get(ecosystem)
        if resolver is None:
            raise UnsupportedEcosystemError(ecosystem)
        return resolver
