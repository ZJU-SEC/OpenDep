from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
NPM_ROOT = CURRENT_FILE.parent
PROJECT_ROOT = CURRENT_FILE.parents[2]
COMMON_DATABASE_ROOT = PROJECT_ROOT / "pre-process" / "common" / "database"

for path in (NPM_ROOT, PROJECT_ROOT, COMMON_DATABASE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from adapters.registry_client import DEFAULT_REGISTRY_BASE_URL, NpmRegistryClient
from loaders.postgres_loader import DEFAULT_SCHEMA_FILE, DEFAULT_TABLE_NAME, NpmPackumentPostgresLoader
from pipeline.package_specs import NpmPackageSpec, load_package_specs
from pipeline.records import NpmPackumentRecord


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="npm-preprocess-build",
        description="Fetch raw npm packuments and store them in PostgreSQL.",
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--package",
        action="append",
        dest="packages",
        default=[],
        help="npm package name input. Can be repeated.",
    )
    source_group.add_argument(
        "--package-file",
        help="Text file containing one npm package name per line.",
    )
    parser.add_argument("--dsn", help="Optional PostgreSQL DSN override.")
    parser.add_argument("--table", default=DEFAULT_TABLE_NAME, help="Destination table name.")
    parser.add_argument(
        "--schema-file",
        help="Optional schema SQL file used with --ensure-schema.",
    )
    parser.add_argument(
        "--ensure-schema",
        action="store_true",
        help="Apply the npm schema SQL before writing records.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip package rows that already exist in the destination table.",
    )
    parser.add_argument(
        "--registry-base-url",
        default=DEFAULT_REGISTRY_BASE_URL,
        help="Base URL of the npm registry used for raw packument fetches.",
    )
    parser.add_argument(
        "--concurrency",
        type=_positive_int,
        default=1,
        help="Maximum number of concurrent npm registry fetches.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output JSON.")
    return parser


def _emit(payload: dict[str, object], *, pretty: bool) -> None:
    if pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=False))


def _status_from_counts(*, stored: int, skipped: int, errors: int) -> str:
    if errors == 0:
        return "ok"
    if stored > 0 or skipped > 0:
        return "partial"
    return "error"


def _fetch_record(registry_client: NpmRegistryClient, package_name: str) -> NpmPackumentRecord:
    download = registry_client.fetch_raw_packument(package_name)
    return NpmPackumentRecord.from_raw_packument(
        name=download.name,
        raw_packument=download.raw_packument,
        source_url=download.source_url,
        fetched_at=download.fetched_at,
        source_rev=download.source_rev,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    package_specs = load_package_specs(specs=args.packages, package_file=args.package_file)

    registry_client = NpmRegistryClient(base_url=args.registry_base_url)
    loader = NpmPackumentPostgresLoader(
        dsn=args.dsn,
        table_name=args.table,
        schema_file=args.schema_file or DEFAULT_SCHEMA_FILE,
    )

    warnings: list[str] = []
    results: list[dict[str, object] | None] = [None] * len(package_specs)
    stored_count = 0
    skipped_count = 0
    error_count = 0

    try:
        if args.ensure_schema:
            loader.ensure_schema()

        table_exists = loader.table_exists()
        if not table_exists:
            _emit(
                {
                    "status": "error",
                    "operation": "build",
                    "message": (
                        f"destination table `{loader.table_name}` does not exist; "
                        "rerun with `--ensure-schema` or apply the schema manually"
                    ),
                    "store": {
                        "backend": "postgres",
                        "table": loader.table_name,
                    },
                },
                pretty=args.pretty,
            )
            return 1

        skip_existing_active = args.skip_existing and table_exists

        pending_fetches: list[tuple[int, NpmPackageSpec]] = []
        for index, spec in enumerate(package_specs):
            item: dict[str, object] = {
                "name": spec.name,
            }
            if skip_existing_active and loader.has_package(spec.name):
                item["status"] = "skipped"
                skipped_count += 1
                results[index] = item
            else:
                pending_fetches.append((index, spec))

        if pending_fetches:
            with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
                future_to_spec = {
                    executor.submit(_fetch_record, registry_client, spec.name): (index, spec)
                    for index, spec in pending_fetches
                }
                for future in as_completed(future_to_spec):
                    index, spec = future_to_spec[future]
                    item: dict[str, object] = {
                        "name": spec.name,
                    }
                    try:
                        record = future.result()
                        loader.upsert_record(record)
                        item.update(record.to_dict())
                        item["status"] = "stored"
                        stored_count += 1
                    except Exception as exc:
                        item["status"] = "error"
                        item["error"] = str(exc)
                        error_count += 1
                    results[index] = item

        payload = {
            "status": _status_from_counts(
                stored=stored_count,
                skipped=skipped_count,
                errors=error_count,
            ),
            "operation": "build",
            "input_count": len(package_specs),
            "requested_count": len([item for item in results if item is not None]),
            "summary": {
                "stored_count": stored_count,
                "skipped_count": skipped_count,
                "error_count": error_count,
            },
            "store": {
                "backend": "postgres",
                "table": loader.table_name,
            },
            "source": {
                "registry_base_url": registry_client.base_url,
                "concurrency": args.concurrency,
            },
            "warnings": warnings,
            "results": [item for item in results if item is not None],
        }
        _emit(payload, pretty=args.pretty)
        return 0 if error_count == 0 else 1
    finally:
        loader.close()


if __name__ == "__main__":
    raise SystemExit(main())
