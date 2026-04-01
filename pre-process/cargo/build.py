from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
CARGO_ROOT = CURRENT_FILE.parent
PROJECT_ROOT = CURRENT_FILE.parents[2]

for path in (CARGO_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from adapters.git_index import GitIndexError, clone_index, describe_index_repo, update_index
from pipeline.layout import DEFAULT_INDEX_URL, SHARED_DATA_ROOT, CargoDataLayout
from pipeline.local_registry import LocalRegistryError, inspect_local_registry, stage_local_registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cargo-preprocess-build",
        description="Manage the shared Cargo preprocess volume and prepare a resolver-consumable local-registry layout.",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--pretty", action="store_true", help="Pretty-print output JSON.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    clone_parser = subparsers.add_parser(
        "clone",
        parents=[common],
        help="Clone crates.io-index into the managed data layout.",
    )
    clone_parser.add_argument(
        "--index-url",
        default=DEFAULT_INDEX_URL,
        help="Source git URL for the managed crates.io-index clone.",
    )
    clone_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing managed index clone.",
    )

    update_parser = subparsers.add_parser(
        "update",
        parents=[common],
        help="Update the managed crates.io-index clone in place.",
    )
    update_parser.add_argument(
        "--force",
        action="store_true",
        help="Discard local modifications before updating the managed index clone.",
    )

    prepare_parser = subparsers.add_parser(
        "prepare-local-registry",
        parents=[common],
        help="Copy the managed index clone into a resolver-consumable local-registry layout.",
    )
    prepare_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing local-registry output directory.",
    )

    return parser


def _emit(payload: dict[str, object], *, pretty: bool) -> None:
    if pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=False))


def _build_inspection_payload(layout: CargoDataLayout, *, operation: str) -> dict[str, object]:
    return {
        "status": "ok",
        "operation": operation,
        "paths": layout.to_dict(),
        "index": describe_index_repo(layout.index_dir),
        "local_registry": inspect_local_registry(layout.local_registry_dir),
    }


def _ensure_docker_shared_volume(layout: CargoDataLayout) -> None:
    if not Path("/.dockerenv").exists():
        raise RuntimeError(
            "Cargo preprocess is Docker-only. Run it via "
            "`docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess ...`."
        )

    expected_root = SHARED_DATA_ROOT.resolve()
    if layout.data_root != expected_root:
        raise RuntimeError(
            f"Cargo preprocess must use the shared volume path {expected_root}; custom data roots are not supported"
        )

    for managed_path in (layout.index_dir, layout.local_registry_dir):
        if not managed_path.is_relative_to(expected_root):
            raise RuntimeError(
                f"Cargo preprocess paths must stay under the shared volume path {expected_root}: {managed_path}"
            )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    layout = CargoDataLayout.from_overrides()

    try:
        _ensure_docker_shared_volume(layout)
        if args.command == "clone":
            clone_index(args.index_url, layout.index_dir, force=args.force)
            payload = _build_inspection_payload(layout, operation="clone")
            payload["source"] = {"index_url": args.index_url}
        elif args.command == "update":
            update_result = update_index(layout.index_dir, force=args.force)
            payload = _build_inspection_payload(layout, operation="update")
            payload["update"] = update_result
        elif args.command == "prepare-local-registry":
            local_registry = stage_local_registry(
                layout.index_dir,
                layout.local_registry_dir,
                force=args.force,
            )
            payload = _build_inspection_payload(layout, operation="prepare-local-registry")
            payload["local_registry"] = local_registry
        else:
            raise RuntimeError(f"unsupported command: {args.command}")
    except (GitIndexError, LocalRegistryError, RuntimeError) as exc:
        _emit(
            {
                "status": "error",
                "operation": args.command,
                "message": str(exc),
                "paths": layout.to_dict(),
            },
            pretty=args.pretty,
        )
        return 1

    _emit(payload, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
