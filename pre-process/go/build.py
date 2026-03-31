from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from pipeline.module_specs import GoModuleRequest, GoModuleSpec, load_module_requests
from pipeline.records import GoModuleModfileRecord


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


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
        help="Go module input in `module` or `module@version` form. Can be repeated.",
    )
    source_group.add_argument(
        "--module-file",
        help="Text file containing one `module` or `module@version` entry per line.",
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
    parser.add_argument(
        "--concurrency",
        type=_positive_int,
        default=1,
        help="Maximum number of concurrent Go proxy fetches.",
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


def _fetch_record(proxy_client: GoProxyClient, module_path: str, version: str) -> GoModuleModfileRecord:
    download = proxy_client.fetch_raw_mod(module_path, version)
    return GoModuleModfileRecord.from_raw_mod(
        module_path=download.module_path,
        version=download.version,
        raw_mod=download.raw_mod,
        source_url=download.source_url,
        fetched_at=download.fetched_at,
    )


def _plan_module_specs(
    requests: list[GoModuleRequest],
    proxy_client: GoProxyClient,
) -> tuple[list[dict[str, object] | None], list[tuple[int, GoModuleSpec]], int]:
    planned_results: list[dict[str, object] | None] = []
    pending_specs: list[tuple[int, GoModuleSpec]] = []
    seen_specs: set[tuple[str, str]] = set()
    error_count = 0

    for request in requests:
        if request.version is not None:
            candidate_versions = (request.version,)
        else:
            try:
                candidate_versions = proxy_client.list_versions(request.module_path)
            except Exception as exc:
                planned_results.append(
                    {
                        "module_path": request.module_path,
                        "status": "error",
                        "error": str(exc),
                    }
                )
                error_count += 1
                continue

            if not candidate_versions:
                planned_results.append(
                    {
                        "module_path": request.module_path,
                        "status": "error",
                        "error": f"go proxy returned no versions for {request.module_path}",
                    }
                )
                error_count += 1
                continue

        for version in candidate_versions:
            key = (request.module_path, version)
            if key in seen_specs:
                continue
            seen_specs.add(key)
            planned_results.append(None)
            pending_specs.append((len(planned_results) - 1, request.to_spec(version)))

    return planned_results, pending_specs, error_count


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    requests = load_module_requests(specs=args.modules, module_file=args.module_file)

    proxy_client = GoProxyClient(base_url=args.proxy_base_url)
    loader = GoModuleModfilePostgresLoader(
        dsn=args.dsn,
        table_name=args.table,
        schema_file=args.schema_file or DEFAULT_SCHEMA_FILE,
    )

    warnings: list[str] = []
    results, pending_specs, error_count = _plan_module_specs(requests, proxy_client)
    stored_count = 0
    skipped_count = 0

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

        pending_fetches: list[tuple[int, GoModuleSpec]] = []
        for index, spec in pending_specs:
            item: dict[str, object] = {
                "module_path": spec.module_path,
                "version": spec.version,
            }
            if skip_existing_active and loader.has_module(spec.module_path, spec.version):
                item["status"] = "skipped"
                skipped_count += 1
                results[index] = item
            else:
                pending_fetches.append((index, spec))

        if pending_fetches:
            with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
                future_to_spec = {
                    executor.submit(_fetch_record, proxy_client, spec.module_path, spec.version): (index, spec)
                    for index, spec in pending_fetches
                }
                for future in as_completed(future_to_spec):
                    index, spec = future_to_spec[future]
                    item: dict[str, object] = {
                        "module_path": spec.module_path,
                        "version": spec.version,
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
            "input_count": len(requests),
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
                "proxy_base_url": proxy_client.base_url,
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
