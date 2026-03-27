from __future__ import annotations


class GatewayError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False, backend_error: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.backend_error = backend_error


class InvalidArgumentError(GatewayError):
    def __init__(self, message: str) -> None:
        super().__init__("INVALID_ARGUMENT", message, retryable=False)


class UnsupportedEcosystemError(GatewayError):
    def __init__(self, ecosystem: str) -> None:
        super().__init__("UNSUPPORTED_ECOSYSTEM", f"unsupported ecosystem: {ecosystem}", retryable=False)


class UnsupportedCommandError(GatewayError):
    def __init__(self, ecosystem: str, command: str) -> None:
        super().__init__(
            "UNSUPPORTED_COMMAND",
            f"command '{command}' is not supported by resolver '{ecosystem}'",
            retryable=False,
        )


class UnsupportedOptionError(GatewayError):
    def __init__(
        self,
        ecosystem: str,
        option_name: str,
        option_value: object,
        supported_values: list[str] | None = None,
    ) -> None:
        details = f"option '{option_name}' is not supported by resolver '{ecosystem}'"
        if option_value is not None:
            details = f"option '{option_name}={option_value}' is not supported by resolver '{ecosystem}'"
        if supported_values:
            supported = ", ".join(supported_values)
            details = f"{details}; supported values: {supported}"
        super().__init__("UNSUPPORTED_OPTION", details, retryable=False)


class ProtocolError(GatewayError):
    def __init__(self, message: str, backend_error: str | None = None) -> None:
        super().__init__("PROTOCOL_ERROR", message, retryable=False, backend_error=backend_error)


class TimeoutGatewayError(GatewayError):
    def __init__(self, message: str) -> None:
        super().__init__("TIMEOUT", message, retryable=True)
