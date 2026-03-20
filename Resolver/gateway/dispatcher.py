from __future__ import annotations

from Resolver.gateway.registry import ResolverRegistry
from Resolver.gateway.response import AdapterResponseNormalizer
from Resolver.gateway.router import ResolverRouter
from Resolver.gateway.runner import ProcessRunner


class GatewayDispatcher:
    def __init__(
        self,
        registry: ResolverRegistry,
        router: ResolverRouter | None = None,
        runner: ProcessRunner | None = None,
        normalizer: AdapterResponseNormalizer | None = None,
    ) -> None:
        self.registry = registry
        self.router = router or ResolverRouter()
        self.runner = runner or ProcessRunner()
        self.normalizer = normalizer or AdapterResponseNormalizer()

    def dispatch(self, request: dict) -> dict:
        resolver = self.router.select_resolver(self.registry, request)
        run_result = self.runner.run(resolver, request)
        return self.normalizer.normalize(request, resolver, run_result)
