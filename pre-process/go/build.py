from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
GO_ROOT = CURRENT_FILE.parent
PROJECT_ROOT = CURRENT_FILE.parents[2]
COMMON_DATABASE_ROOT = PROJECT_ROOT / "pre-process" / "common" / "database"

for path in (GO_ROOT, PROJECT_ROOT, COMMON_DATABASE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from adapters.proxy_client import DEFAULT_PROXY_BASE_URL, GoProxyClient
from loaders.postgres_loader import DEFAULT_SCHEMA_FILE, DEFAULT_TABLE_NAME, GoModuleModfilePostgresLoader
from pipeline.module_specs import load_module_specs
from pipeline.records import GoModuleModfileRecord


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="go-preprocess-build",
        description="Fetch raw go.mod files from a Go proxy and store them in PostgreSQL.",
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--module",
        action="append",
        dest="modules",
        default=[],
        help="Explicit Go module version in `module@version` form. Can be repeated.",
    )
    source_group.add_argument(
        "--module-file",
        help="Text file containing one `module@version` entry per line.",
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
        help="Apply the Go schema SQL before writing records.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip module versions that already exist in the destination table.",
    )
    parser.add_argument(
        "--proxy-base-url",
        default=DEFAULT_PROXY_BASE_URL,
        help="Base URL of the Go proxy used for raw .mod fetches.",
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    specs = load_module_specs(specs=args.modules, module_file=args.module_file)

    proxy_client = GoProxyClient(base_url=args.proxy_base_url)
    loader = GoModuleModfilePostgresLoader(
        dsn=args.dsn,
        table_name=args.table,
        schema_file=args.schema_file or DEFAULT_SCHEMA_FILE,
    )

    warnings: list[str] = []
    results: list[dict[str, object]] = []
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

        for spec in specs:
            item: dict[str, object] = {
                "module_path": spec.module_path,
                "version": spec.version,
            }
            try:
                if skip_existing_active and loader.has_module(spec.module_path, spec.version):
                    item["status"] = "skipped"
                    skipped_count += 1
                else:
                    download = proxy_client.fetch_raw_mod(spec.module_path, spec.version)
                    record = GoModuleModfileRecord.from_raw_mod(
                        module_path=download.module_path,
                        version=download.version,
                        raw_mod=download.raw_mod,
                        source_url=download.source_url,
                        fetched_at=download.fetched_at,
                    )
                    loader.upsert_record(record)
                    item.update(record.to_dict())
                    item["status"] = "stored"
                    stored_count += 1
            except Exception as exc:
                item["status"] = "error"
                item["error"] = str(exc)
                error_count += 1
            results.append(item)

        payload = {
            "status": _status_from_counts(
                stored=stored_count,
                skipped=skipped_count,
                errors=error_count,
            ),
            "operation": "build",
            "requested_count": len(specs),
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
                "proxy_base_url": proxy_client.base_url,
            },
            "warnings": warnings,
            "results": results,
        }
        _emit(payload, pretty=args.pretty)
        return 0 if error_count == 0 else 1
    finally:
        loader.close()


if __name__ == "__main__":
    raise SystemExit(main())
