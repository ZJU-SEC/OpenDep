from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError, URLError
import sys
from pathlib import Path
from typing import Any


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[5]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from resolving.containerization.images.pip.backend import BACKEND_NAME, BACKEND_VERSION
from resolving.containerization.images.pip.backend.config import BackendConfig, normalize_metadata_mode
from resolving.containerization.images.pip.backend.errors import BackendError
from resolving.containerization.images.pip.backend.graph import build_graph_result
from resolving.containerization.images.pip.backend.indexer import IndexerService
from resolving.containerization.images.pip.backend.metadata_sources import build_metadata_source
from resolving.containerization.images.pip.backend.resolver_core import ResolverCore
from resolving.containerization.images.pip.backend.stores import build_index_store

try:
    from packaging.version import InvalidVersion, Version
except ImportError:  # pragma: no cover - fallback for minimal pip environments
    from pip._vendor.packaging.version import InvalidVersion, Version


def _parse_metadata_mode(value: str) -> str:
    normalized = normalize_metadata_mode(value)
    if normalized in {"online", "indexed"}:
        return normalized
    raise argparse.ArgumentTypeError("pip metadata mode must be `online` or `indexed`")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pip-backend",
        description="Bootstrap CLI for the pip dependency backend.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")

    subparsers.add_parser("health", help="Show backend bootstrap health.")
    subparsers.add_parser("describe", help="Describe the current backend skeleton.")

    resolve = subparsers.add_parser("resolve", help="Resolve a dependency graph.")
    resolve.add_argument("--name", required=True, help="Package name to resolve.")
    resolve.add_argument("--version", help="Package version to resolve.")
    resolve.add_argument(
        "--mode",
        type=_parse_metadata_mode,
        metavar="{online,indexed}",
        help="Optional metadata mode override for this invocation. `live` is accepted as a compatibility alias.",
    )
    resolve.add_argument(
        "--format",
        default="graph",
        choices=("graph",),
        help="Result format. Only graph is currently supported.",
    )

    index = subparsers.add_parser(
        "index",
        help="Extract dependency metadata and write it into the indexed store.",
    )
    index.add_argument("--name", required=True, help="Package name to index.")
    index.add_argument(
        "--version",
        action="append",
        dest="versions",
        help="Specific package version to index. Can be provided multiple times.",
    )
    index.add_argument(
        "--limit",
        type=int,
        help="When no explicit version is provided, index only the latest N versions.",
    )
    index.add_argument(
        "--include-yanked",
        action="store_true",
        help="Include yanked releases when enumerating versions from the source index.",
    )
    index.add_argument(
        "--skip-existing",
        action="store_true",
        help="Do not rewrite releases that already exist in the indexed store.",
    )
    index.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop indexing after the first failed release extraction.",
    )

    return parser


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _health_payload(config: BackendConfig) -> dict[str, Any]:
    return {
        "backend": BACKEND_NAME,
        "version": BACKEND_VERSION,
        "status": "ok",
        "bootstrap": True,
        "packages": [
            "resolver_core",
            "metadata_sources",
            "inspectors",
            "stores",
            "indexer",
        ],
        "config": config.as_dict(),
    }


def _describe_payload(config: BackendConfig) -> dict[str, Any]:
    return {
        "backend": BACKEND_NAME,
        "version": BACKEND_VERSION,
        "scope": "active",
        "implemented_tasks": [
            "PIP-T01",
            "PIP-T02",
            "PIP-T03",
            "PIP-T04",
            "PIP-T05",
            "PIP-T06",
            "PIP-T07",
            "PIP-T08",
            "PIP-T09",
            "PIP-T10",
            "PIP-T11",
            "PIP-T12",
            "PIP-T13",
            "PIP-T14",
        ],
        "pending_tasks": [],
        "config": config.as_dict(),
    }


def _error_payload(error: BackendError) -> dict[str, Any]:
    return error.to_dict()


def _select_root_version(name: str, requested_version: str | None, source) -> str:
    if requested_version:
        return requested_version

    versions = source.list_versions(name)
    if not versions:
        raise BackendError(
            "PACKAGE_NOT_FOUND",
            f"package `{name}` was not found",
            retryable=False,
        )

    non_yanked = [record for record in versions if not record.yanked]
    candidates = non_yanked or versions

    stable = [record for record in candidates if not _is_prerelease(record.version)]
    selected = stable[0] if stable else candidates[0]
    return selected.version


def _is_prerelease(version: str) -> bool:
    try:
        return Version(version).is_prerelease
    except InvalidVersion:
        return False


def _load_root_release(source, package_name: str, root_version: str):
    try:
        return source.warm(package_name, root_version)
    except KeyError as exc:
        versions = source.list_versions(package_name)
        if not versions:
            raise BackendError(
                "PACKAGE_NOT_FOUND",
                f"package `{package_name}` was not found",
                retryable=False,
                backend_error=exc.__class__.__name__,
            ) from exc
        raise BackendError(
            "VERSION_NOT_FOUND",
            f"version `{root_version}` was not found for package `{package_name}`",
            retryable=False,
            backend_error=exc.__class__.__name__,
        ) from exc
    except HTTPError as exc:
        status_code = getattr(exc, "code", None)
        if status_code == 404:
            raise BackendError(
                "VERSION_NOT_FOUND",
                f"version `{root_version}` was not found for package `{package_name}`",
                retryable=False,
                backend_error=f"HTTP {status_code}",
            ) from exc
        raise BackendError(
            "DATA_SOURCE_UNAVAILABLE",
            f"failed to fetch metadata for `{package_name}` from upstream index",
            retryable=True,
            backend_error=f"HTTP {status_code}" if status_code is not None else exc.__class__.__name__,
        ) from exc
    except URLError as exc:
        raise BackendError(
            "DATA_SOURCE_UNAVAILABLE",
            f"failed to reach upstream metadata source for `{package_name}`",
            retryable=True,
            backend_error=exc.reason if hasattr(exc, "reason") else exc.__class__.__name__,
        ) from exc
    except BackendError:
        raise
    except Exception as exc:
        raise BackendError(
            "INTERNAL_ERROR",
            f"failed to load release metadata for `{package_name}`",
            retryable=False,
            backend_error=exc.__class__.__name__,
        ) from exc


def _raise_source_error(package_name: str, exc: Exception) -> None:
    if isinstance(exc, HTTPError):
        status_code = getattr(exc, "code", None)
        if status_code == 404:
            raise BackendError(
                "PACKAGE_NOT_FOUND",
                f"package `{package_name}` was not found",
                retryable=False,
                backend_error=f"HTTP {status_code}",
            ) from exc
        raise BackendError(
            "DATA_SOURCE_UNAVAILABLE",
            f"failed to fetch metadata for `{package_name}` from upstream index",
            retryable=True,
            backend_error=f"HTTP {status_code}" if status_code is not None else exc.__class__.__name__,
        ) from exc
    if isinstance(exc, URLError):
        raise BackendError(
            "DATA_SOURCE_UNAVAILABLE",
            f"failed to reach upstream metadata source for `{package_name}`",
            retryable=True,
            backend_error=str(exc.reason) if hasattr(exc, "reason") else exc.__class__.__name__,
        ) from exc
    raise exc


def _resolve_payload(config: BackendConfig, package_name: str, version: str | None, mode: str, format_name: str) -> dict[str, Any]:
    if format_name != "graph":
        raise BackendError(
            "INVALID_ARGUMENT",
            f"unsupported pip backend format `{format_name}`",
            retryable=False,
        )

    source = build_metadata_source(config, mode_override=mode)
    try:
        try:
            root_version = _select_root_version(package_name, version, source)
        except (HTTPError, URLError) as exc:
            _raise_source_error(package_name, exc)
        root_record = _load_root_release(source, package_name, root_version)
        resolver = ResolverCore(source)
        try:
            resolution_result = resolver.resolve([f"{root_record.name}=={root_record.version}"])
        except (HTTPError, URLError) as exc:
            _raise_source_error(package_name, exc)
        return build_graph_result(
            package_name=package_name,
            requested_version=version,
            resolution_result=resolution_result,
            metadata_mode=mode,
        )
    finally:
        source.close()


def _index_payload(
    config: BackendConfig,
    package_name: str,
    versions: list[str] | None,
    include_yanked: bool,
    skip_existing: bool,
    fail_fast: bool,
    limit: int | None,
) -> tuple[dict[str, Any], int]:
    source = build_metadata_source(config, mode_override="online")
    try:
        store = build_index_store(config)
    except Exception:
        source.close()
        raise

    try:
        service = IndexerService(
            source,
            store,
            target_backend=config.index_backend or "postgres",
        )
        try:
            result = service.index_project(
                package_name,
                versions=versions,
                include_yanked=include_yanked,
                skip_existing=skip_existing,
                fail_fast=fail_fast,
                limit=limit,
            )
        except (HTTPError, URLError) as exc:
            _raise_source_error(package_name, exc)
        payload = result.to_dict()
        payload["store"] = {
            "backend": config.index_backend or "postgres",
            "table": config.index_table,
        }
        return payload, 0 if not result.failed else 1
    finally:
        source.close()
        store.close()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = BackendConfig.from_env()

    if args.command == "health":
        _emit(_health_payload(config))
        return 0

    if args.command == "describe":
        _emit(_describe_payload(config))
        return 0

    try:
        if args.command == "index":
            payload, exit_code = _index_payload(
                config,
                args.name,
                args.versions,
                args.include_yanked,
                args.skip_existing,
                args.fail_fast,
                args.limit,
            )
            _emit(payload)
            return exit_code

        resolve_mode = args.mode or config.metadata_mode
        payload = _resolve_payload(
            config,
            args.name,
            args.version,
            resolve_mode,
            args.format,
        )
    except BackendError as error:
        _emit(_error_payload(error))
        return 1
    except Exception as exc:
        _emit(
            _error_payload(
                BackendError(
                    "INTERNAL_ERROR",
                    "unexpected pip backend failure",
                    retryable=False,
                    backend_error=exc.__class__.__name__,
                )
            )
        )
        return 1

    _emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
