from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessRunResult:
    timeout: bool
    stdout: str
    stderr: str
    exit_code: int | None

    def raw_payload(self) -> dict:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
        }
