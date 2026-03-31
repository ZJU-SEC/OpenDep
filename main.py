from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))


from resolving.gateway.config import default_config_path, load_config
from resolving.gateway.registry import ResolverRegistry
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
PIP_MODE_HELP = "pip metadata mode. Supported values: live, indexed."
PIP_INDEX_DSN_HELP = "PostgreSQL DSN used by the pip indexed metadata store."
PIP_INDEX_TABLE_HELP = "PostgreSQL table name used by the pip indexed metadata store."
PIP_INDEX_BACKEND_HELP = "Indexed metadata backend for pip. Defaults to postgres."
GO_MODE_HELP = "go metadata mode. Supported values: online, indexed."
GO_INDEX_DSN_HELP = "PostgreSQL DSN used by the go indexed metadata store."
GO_INDEX_TABLE_HELP = "PostgreSQL table name used by the go indexed metadata store."
GO_INDEX_FALLBACK_HELP = "Allow go indexed mode to fall back to online metadata when indexed data is missing. Enabled by default."
NPM_MODE_HELP = "npm metadata mode. Supported values: online, indexed."
NPM_INDEX_DSN_HELP = "PostgreSQL DSN used by the npm indexed metadata store."
NPM_INDEX_TABLE_HELP = "PostgreSQL table name used by the npm indexed metadata store."
NPM_INDEX_FALLBACK_HELP = "Allow npm indexed mode to fall back to online metadata when indexed data is missing. Enabled by default."
NPM_REGISTRY_BASE_URL_HELP = "Base URL used by npm online fetches and indexed fallback."


def add_pip_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pip-mode", choices=("live", "indexed"), help=PIP_MODE_HELP)
    parser.add_argument("--pip-index-dsn", help=PIP_INDEX_DSN_HELP)
    parser.add_argument("--pip-index-table", help=PIP_INDEX_TABLE_HELP)
    parser.add_argument("--pip-index-backend", help=PIP_INDEX_BACKEND_HELP)
    parser.add_argument(
        "--pip-index-fallback-to-live",
        action="store_true",
        help="Allow pip indexed mode to fall back to live metadata when indexed data is missing.",
    )


def add_go_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--go-mode", choices=("online", "indexed"), help=GO_MODE_HELP)
    parser.add_argument("--go-index-dsn", help=GO_INDEX_DSN_HELP)
    parser.add_argument("--go-index-table", help=GO_INDEX_TABLE_HELP)
    parser.add_argument(
        "--go-index-fallback-to-online",
        action="store_true",
        help=GO_INDEX_FALLBACK_HELP,
    )


def add_npm_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--npm-mode", choices=("online", "indexed"), help=NPM_MODE_HELP)
    parser.add_argument("--npm-index-dsn", help=NPM_INDEX_DSN_HELP)
    parser.add_argument("--npm-index-table", help=NPM_INDEX_TABLE_HELP)
    parser.add_argument("--npm-registry-base-url", help=NPM_REGISTRY_BASE_URL_HELP)
    parser.add_argument(
        "--npm-index-fallback-to-online",
        action="store_true",
        help=NPM_INDEX_FALLBACK_HELP,
    )


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
    add_pip_runtime_args(resolve)
    add_go_runtime_args(resolve)
    add_npm_runtime_args(resolve)

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
    add_pip_runtime_args(list_cmd)
    add_go_runtime_args(list_cmd)
    add_npm_runtime_args(list_cmd)

    health = subparsers.add_parser(
        "health",
        help="Check resolver and backend health.",
        description="Check resolver availability and backend readiness.",
    )
    health.add_argument("--ecosystem", required=True, help=ECOSYSTEM_HELP)
    health.add_argument("--timeout-ms", type=int, help=TIMEOUT_HELP)
    add_pip_runtime_args(health)
    add_go_runtime_args(health)
    add_npm_runtime_args(health)

    capabilities = subparsers.add_parser(
        "capabilities",
        help="Show supported commands and features.",
        description="Show the commands, formats, and features supported by the selected resolver.",
    )
    capabilities.add_argument("--ecosystem", required=True, help=ECOSYSTEM_HELP)
    capabilities.add_argument("--timeout-ms", type=int, help=TIMEOUT_HELP)
    add_pip_runtime_args(capabilities)
    add_go_runtime_args(capabilities)
    add_npm_runtime_args(capabilities)
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


def apply_runtime_overrides(args: argparse.Namespace) -> None:
    ecosystem = getattr(args, "ecosystem", None)
    if ecosystem == "pip":
        if getattr(args, "pip_mode", None):
            os.environ["PIP_METADATA_MODE"] = args.pip_mode
        if getattr(args, "pip_index_dsn", None):
            os.environ["PIP_INDEX_DSN"] = args.pip_index_dsn
        if getattr(args, "pip_index_table", None):
            os.environ["PIP_INDEX_TABLE"] = args.pip_index_table
        if getattr(args, "pip_index_backend", None):
            os.environ["PIP_INDEX_BACKEND"] = args.pip_index_backend
        if getattr(args, "pip_index_fallback_to_live", False):
            os.environ["PIP_INDEX_FALLBACK_TO_LIVE"] = "true"
        return

    if ecosystem == "go":
        if getattr(args, "go_mode", None):
            os.environ["GO_METADATA_MODE"] = args.go_mode
        if getattr(args, "go_index_dsn", None):
            os.environ["GO_INDEX_DSN"] = args.go_index_dsn
        if getattr(args, "go_index_table", None):
            os.environ["GO_INDEX_TABLE"] = args.go_index_table
        if getattr(args, "go_index_fallback_to_online", False):
            os.environ["GO_INDEX_FALLBACK_TO_ONLINE"] = "true"
        return

    if ecosystem == "npm":
        if getattr(args, "npm_mode", None):
            os.environ["NPM_METADATA_MODE"] = args.npm_mode
        if getattr(args, "npm_index_dsn", None):
            os.environ["NPM_INDEX_DSN"] = args.npm_index_dsn
        if getattr(args, "npm_index_table", None):
            os.environ["NPM_INDEX_TABLE"] = args.npm_index_table
        if getattr(args, "npm_registry_base_url", None):
            os.environ["NPM_REGISTRY_BASE_URL"] = args.npm_registry_base_url
        if getattr(args, "npm_index_fallback_to_online", False):
            os.environ["NPM_INDEX_FALLBACK_TO_ONLINE"] = "true"


def main() -> int:
    args = parse_args()
    apply_runtime_overrides(args)
    request = build_request(args)
    config_path = args.config or str(default_config_path(args.ecosystem))
    registry = ResolverRegistry(load_config(config_path, ecosystem=args.ecosystem))
    service = GatewayService(registry)
    response = service.handle(request)

    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
