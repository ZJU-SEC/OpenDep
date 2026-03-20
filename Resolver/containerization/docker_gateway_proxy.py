from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from Resolver.containerization.runtime.adapter_runtime import AdapterMetadata, emit_payload, error_response


PROXY_VERSION = "container-proxy-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Proxy Gateway stdin/stdout through docker compose run")
    parser.add_argument("--service", required=True, help="Compose service name")
    parser.add_argument("--ecosystem", required=True, help="Resolver ecosystem")
    parser.add_argument(
        "--compose-file",
        default=str(CURRENT_FILE.parent / "docker-compose.yml"),
        help="Path to docker compose file",
    )
    parser.add_argument("--project-name", default="resolver-stack", help="Compose project name")
    return parser.parse_args()


def build_metadata(service: str, ecosystem: str) -> AdapterMetadata:
    return AdapterMetadata(
        name=f"container-proxy:{service}",
        adapter_version=PROXY_VERSION,
        backend_version=None,
        ecosystem=ecosystem,
    )


def load_request(raw_request: str) -> dict:
    if not raw_request.strip():
        return {}
    try:
        payload = json.loads(raw_request)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def emit_infra_error(
    raw_request: str,
    metadata: AdapterMetadata,
    start_time: float,
    message: str,
    backend_error: str | None,
) -> int:
    request = load_request(raw_request)
    emit_payload(
        error_response(
            request,
            metadata,
            "BACKEND_MISCONFIGURED",
            message,
            backend_error,
            False,
            start_time,
        )
    )
    return 1


def main() -> int:
    args = parse_args()
    start_time = time.perf_counter()
    metadata = build_metadata(args.service, args.ecosystem)
    raw_request = sys.stdin.read()

    command = [
        "docker",
        "compose",
        "-f",
        str(Path(args.compose_file).resolve()),
        "-p",
        args.project_name,
        "run",
        "--rm",
        "--no-deps",
        "-T",
        args.service,
    ]

    try:
        completed = subprocess.run(
            command,
            input=raw_request,
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            check=False,
        )
    except FileNotFoundError as exc:
        return emit_infra_error(raw_request, metadata, start_time, "docker executable not found in PATH", str(exc))
    except OSError as exc:
        return emit_infra_error(raw_request, metadata, start_time, "failed to start docker compose", str(exc))

    if completed.returncode != 0 and not completed.stdout.strip():
        return emit_infra_error(
            raw_request,
            metadata,
            start_time,
            "containerized resolver failed before emitting adapter JSON",
            completed.stderr.strip() or None,
        )

    sys.stdout.write(completed.stdout)
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
