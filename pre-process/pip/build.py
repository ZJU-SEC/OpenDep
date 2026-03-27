from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PIP_ROOT = CURRENT_FILE.parent
PROJECT_ROOT = CURRENT_FILE.parents[2]
COMMON_UTILS_ROOT = PROJECT_ROOT / "pre-process" / "common" / "utils"

for path in (PIP_ROOT, PROJECT_ROOT, COMMON_UTILS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from adapters.manifest import ManifestAdapter
from adapters.request_adapter import BuildRequestAdapter
from loaders.postgres_loader import DEFAULT_SCHEMA_FILE, DEFAULT_TABLE_NAME, PipMetadataPostgresLoader
from pipeline.batch_runner import PipBatchJobRunner
from pipeline.build_service import PipBuildService
from retry import RetrySettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pip-preprocess-build",
        description="Run pip preprocessing jobs for local artifacts or package/version requests.",
    )
    parser.add_argument("artifacts", nargs="*", help="One or more local wheel / sdist / egg artifact paths.")
    parser.add_argument("--manifest", help="Optional JSON manifest describing batch jobs.")
    parser.add_argument(
        "--project",
        dest="projects",
        action="append",
        default=[],
        help="Package spec to preprocess. Use `name` for latest planning or `name==version` for an explicit version. Can be repeated.",
    )
    parser.add_argument(
        "--project-file",
        help="Text file containing one PyPI package spec per line. Blank lines and `#` comments are ignored.",
    )
    parser.add_argument("--name", help="Optional package name override for a single artifact invocation.")
    parser.add_argument("--version", help="Optional package version override for a single artifact invocation.")
    parser.add_argument("--limit", type=int, help="When planning package versions, process only the latest N releases.")
    parser.add_argument(
        "--include-yanked",
        action="store_true",
        help="Include yanked releases when planning versions from the package index.",
    )
    parser.add_argument("--cache-dir", help="Optional cache directory for JSON metadata and downloaded artifacts.")
    parser.add_argument("--mirror-dir", help="Optional local PyPI mirror root used before remote download.")
    parser.add_argument(
        "--pypi-json-base-url",
        default="https://pypi.org/pypi",
        help="Base URL for PyPI JSON APIs. Can also point at a local file:// mirror in tests.",
    )
    parser.add_argument(
        "--http-user-agent",
        default="OpenDep-Pip-preprocess/0.1",
        help="User-Agent header used for JSON and artifact fetches.",
    )
    parser.add_argument("--dsn", help="Optional PostgreSQL DSN override.")
    parser.add_argument("--table", default=DEFAULT_TABLE_NAME, help="Destination table name.")
    parser.add_argument("--schema-file", help="Optional schema SQL file used with --ensure-schema.")
    parser.add_argument("--ensure-schema", action="store_true", help="Apply schema SQL before writing records.")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip releases that already exist in the target indexed table.",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Plan the selected versions and only fill missing indexed releases. Implies `--skip-existing` behavior.",
    )
    parser.add_argument(
        "--state-file",
        help="Optional JSONL state file used to record completed releases and skip them on reruns.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run extraction and validation without writing records into PostgreSQL.",
    )
    parser.add_argument(
        "--cleanup-downloaded-artifacts",
        action="store_true",
        help="Delete remotely downloaded artifacts after they have been processed successfully.",
    )
    parser.add_argument("--failure-log", help="Optional JSONL file used to persist failures.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop the batch after the first failed job.")
    parser.add_argument(
        "--no-legacy-fallback",
        action="store_true",
        help="Disable the legacy fallback extractor when the resolver inspector path fails.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output JSON.")
    return parser


def _emit(payload: dict[str, object], *, pretty: bool) -> None:
    if pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=False))


def _load_requests(args):
    if args.manifest:
        if args.artifacts or args.projects or args.project_file:
            raise ValueError("direct `artifacts` / `--project` / `--project-file` inputs cannot be used together with `--manifest`")
        if args.name or args.version or args.limit or args.include_yanked or args.mirror_dir:
            raise ValueError("direct artifact / project overrides cannot be combined with `--manifest`")
        return ManifestAdapter().load(args.manifest)

    return BuildRequestAdapter().from_cli_args(args)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    requests = _load_requests(args)
    loader = None if args.dry_run else PipMetadataPostgresLoader(
        dsn=args.dsn,
        table_name=args.table,
        schema_file=args.schema_file or DEFAULT_SCHEMA_FILE,
    )
    retry_settings = RetrySettings.from_env()
    batch_runner = PipBatchJobRunner(loader=loader, table_name=args.table, retry_settings=retry_settings)
    service = PipBuildService(
        batch_runner=batch_runner,
        cache_dir=args.cache_dir,
        pypi_json_base_url=args.pypi_json_base_url,
        http_user_agent=args.http_user_agent,
        retry_settings=retry_settings,
        table_name=args.table,
    )

    try:
        summary = service.run(
            requests,
            ensure_schema=args.ensure_schema,
            allow_legacy_fallback=not args.no_legacy_fallback,
            failure_log=args.failure_log,
            fail_fast=args.fail_fast,
            skip_existing=args.skip_existing,
            backfill=args.backfill,
            state_file=args.state_file,
            cleanup_downloaded_artifacts=args.cleanup_downloaded_artifacts,
        )
        _emit(summary.to_dict(), pretty=args.pretty)
        return 0 if summary.status != "error" else 1
    finally:
        if loader is not None:
            loader.close()


if __name__ == "__main__":
    raise SystemExit(main())
