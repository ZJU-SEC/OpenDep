from __future__ import annotations

from typing import Any

from resolving.gateway.errors import UnsupportedCommandError, UnsupportedOptionError
from resolving.gateway.registry import ResolverRegistry


class ResolverRouter:
    def select_resolver(self, registry: ResolverRegistry, request: dict[str, Any]) -> dict[str, Any]:
        resolver = registry.require(request["ecosystem"])
        self.validate_command(resolver, request)
        self.validate_format(resolver, request)
        return resolver

    def validate_command(self, resolver: dict[str, Any], request: dict[str, Any]) -> None:
        command = request["command"]
        supported = resolver.get("capabilities", {}).get("commands", [])
        if supported and command not in supported:
            raise UnsupportedCommandError(resolver["ecosystem"], command)

    def validate_format(self, resolver: dict[str, Any], request: dict[str, Any]) -> None:
        if request.get("command") != "resolve":
            return

        options = request.get("options")
        if not isinstance(options, dict):
            return

        requested_format = options.get("format")
        if not requested_format:
            return

        supported_formats = resolver.get("capabilities", {}).get("formats", [])
        if supported_formats and requested_format not in supported_formats:
            raise UnsupportedOptionError(
                resolver["ecosystem"],
                "format",
                requested_format,
                supported_values=[str(value) for value in supported_formats],
            )


def route_request(resolver: dict[str, Any], request: dict[str, Any]) -> None:
    router = ResolverRouter()
    router.validate_command(resolver, request)
    router.validate_format(resolver, request)
