from __future__ import annotations

import json
import subprocess

from resolving.gateway.config import build_env
from resolving.gateway.models import ProcessRunResult


class ProcessRunner:
    def run(self, resolver: dict, request: dict) -> ProcessRunResult:
        timeout_ms = request.get("options", {}).get("timeout_ms") or resolver.get("timeout_ms", 60000)
        payload = json.dumps(request, ensure_ascii=False)

        try:
            completed = subprocess.run(
                resolver["command"],
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout_ms / 1000,
                cwd=resolver.get("workdir"),
                env=build_env(resolver.get("env")),
            )
            return ProcessRunResult(
                timeout=False,
                stdout=completed.stdout,
                stderr=completed.stderr,
                exit_code=completed.returncode,
            )
        except subprocess.TimeoutExpired as exc:
            return ProcessRunResult(
                timeout=True,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                exit_code=None,
            )


def run_process_resolver(resolver: dict, request: dict) -> dict:
    result = ProcessRunner().run(resolver, request)
    return {
        "timeout": result.timeout,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
    }
