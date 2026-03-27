from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BackendError(Exception):
    code: str
    message: str
    retryable: bool = False
    backend_error: str | None = None

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "error",
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "backend_error": self.backend_error,
        }
