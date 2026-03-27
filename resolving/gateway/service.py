from __future__ import annotations

from resolving.gateway.contract import validate_request
from resolving.gateway.dispatcher import GatewayDispatcher
from resolving.gateway.errors import GatewayError, InvalidArgumentError
from resolving.gateway.registry import ResolverRegistry
from resolving.gateway.response import GatewayResponseFactory


class GatewayService:
    def __init__(
        self,
        registry: ResolverRegistry,
        dispatcher: GatewayDispatcher | None = None,
        response_factory: GatewayResponseFactory | None = None,
    ) -> None:
        self.registry = registry
        self.dispatcher = dispatcher or GatewayDispatcher(registry)
        self.response_factory = response_factory or GatewayResponseFactory()

    def handle(self, request: dict) -> dict:
        request_errors = validate_request(request)
        if request_errors:
            return self.response_factory.error_response(
                request,
                InvalidArgumentError("; ".join(request_errors)),
                resolver_name="resolver-gateway",
                adapter_version="v1",
                backend_version=None,
            )

        try:
            return self.dispatcher.dispatch(request)
        except GatewayError as exc:
            return self.response_factory.error_response(
                request,
                exc,
                resolver_name="resolver-gateway",
                adapter_version="v1",
                backend_version=None,
            )
