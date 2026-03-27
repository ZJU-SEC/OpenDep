from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))


from resolving.gateway.config import default_config_path, load_config
from resolving.gateway.registry import resolvingRegistry
from resolving.gateway.service import GatewayService


DESCRIPTION = (
    "OpenDep resolver CLI. "
    "This entrypoint routes requests through the resolving gateway and automatically "
    "selects the recommended resolver registry for the requested ecosystem unless "
    "--config is provided explicitly."
)

EPILOG = """Examples:
  python3 main.py capabilities --ecosystem go
  python3 main.py health --ecosystem npm
  python3 main.py resolve --ecosystem maven --name org.apache.logging.log4j:log4j-core --version 2.23.1 --format graph
  python3 main.py list --ecosystem go --name github.com/kubernetes/apimachinery --version v0.35.2"""

ECOSYSTEM_HELP = "Target ecosystem such as npm, maven, cargo, go, or pip."
TIMEOUT_HELP = "Optional request timeout in milliseconds."
RETURN_RAW_HELP = "Preserve backend-native stdout, stderr, and payload data in the response."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name if sys.argv else "main.py",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        help=(
            "Optional resolver registry override. When omitted, the CLI auto-selects "
            "the recommended registry for the requested ecosystem."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")

    resolve = subparsers.add_parser(
        "resolve",
        help="Resolve a dependency graph.",
        description="Resolve a dependency graph for a package or module.",
    )
    resolve.add_argument("--ecosystem", required=True, help=ECOSYSTEM_HELP)
    resolve.add_argument("--name", required=True, help="Package or module name to resolve.")
    resolve.add_argument("--version", help="Package or module version to resolve.")
    resolve.add_argument(
        "--format",
        default="graph",
        help="Requested result format. Supported values depend on the selected ecosystem.",
    )
    resolve.add_argument("--timeout-ms", type=int, help=TIMEOUT_HELP)
    resolve.add_argument("--return-raw", action="store_true", help=RETURN_RAW_HELP)

    list_cmd = subparsers.add_parser(
        "list",
        help="List dependency entries when supported.",
        description="List dependency entries when supported by the selected resolver.",
    )
    list_cmd.add_argument("--ecosystem", required=True, help=ECOSYSTEM_HELP)
    list_cmd.add_argument("--name", required=True, help="Package or module name to inspect.")
    list_cmd.add_argument("--version", help="Package or module version to inspect.")
    list_cmd.add_argument("--timeout-ms", type=int, help=TIMEOUT_HELP)
    list_cmd.add_argument("--return-raw", action="store_true", help=RETURN_RAW_HELP)

    health = subparsers.add_parser(
        "health",
        help="Check resolver and backend health.",
        description="Check resolver availability and backend readiness.",
    )
    health.add_argument("--ecosystem", required=True, help=ECOSYSTEM_HELP)
    health.add_argument("--timeout-ms", type=int, help=TIMEOUT_HELP)

    capabilities = subparsers.add_parser(
        "capabilities",
        help="Show supported commands and features.",
        description="Show the commands, formats, and features supported by the selected resolver.",
    )
    capabilities.add_argument("--ecosystem", required=True, help=ECOSYSTEM_HELP)
    capabilities.add_argument("--timeout-ms", type=int, help=TIMEOUT_HELP)
    return parser.parse_args()


def build_request(args: argparse.Namespace) -> dict:
    request = {
        "schema_version": "1.0",
        "request_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "command": args.command,
        "ecosystem": args.ecosystem,
        "options": {},
        "context": {"caller": "gateway-cli"},
    }

    if getattr(args, "timeout_ms", None):
        request["options"]["timeout_ms"] = args.timeout_ms

    if args.command in {"resolve", "list"}:
        request["package"] = {"name": args.name, "version": args.version}
        if args.command == "resolve":
            request["options"]["format"] = args.format
        request["options"]["return_raw"] = args.return_raw

    return request


def main() -> int:
    args = parse_args()
    request = build_request(args)
    config_path = args.config or str(default_config_path(args.ecosystem))
    registry = resolvingRegistry(load_config(config_path, ecosystem=args.ecosystem))
    service = GatewayService(registry)
    response = service.handle(request)

    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
