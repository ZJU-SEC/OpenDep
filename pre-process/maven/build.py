from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
MAVEN_ROOT = CURRENT_FILE.parent
PROJECT_ROOT = CURRENT_FILE.parents[2]
COMMON_UTILS_ROOT = PROJECT_ROOT / "pre-process" / "common" / "utils"

for path in (MAVEN_ROOT, PROJECT_ROOT, COMMON_UTILS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from jsonl import append_jsonl
from adapters.manifest import ManifestAdapter
from adapters.request_adapter import BuildRequestAdapter
from pipeline.batch_warm_service import BatchWarmItemResult, BatchWarmSummary, MavenBatchWarmService
from pipeline.crawl_planner import MavenCrawlPlanner, SYNC_MODES


def _add_common_execution_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repository-root", help="Override the local Maven repository root used for writes.")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip already warmed and valid local POM / metadata files.",
    )
    parser.add_argument(
        "--state-file",
        help="Optional JSONL state file used to record completed work and resume later runs.",
    )
    parser.add_argument("--failure-log", help="Optional JSONL file used to persist structured failures.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop the batch after the first error result.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output JSON.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maven-preprocess-build",
        description="Warm Maven POMs and metadata into a shared local .m2 repository.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    warm_parser = subparsers.add_parser(
        "warm",
        help="Warm explicit Maven coordinates, coordinate files, or manifests.",
    )
    warm_parser.add_argument("coordinates", nargs="*", help="One or more Maven coordinates in groupId:artifactId:version form.")
    warm_parser.add_argument(
        "--coordinate",
        action="append",
        help="Additional explicit Maven coordinate. Can be repeated.",
    )
    warm_parser.add_argument(
        "--gav",
        action="append",
        dest="gavs",
        default=[],
        help="Alias of --coordinate. Can be repeated.",
    )
    warm_parser.add_argument("--coordinate-file", help="Text file containing one Maven coordinate per line.")
    warm_parser.add_argument("--manifest", help="JSON manifest describing Maven warm jobs.")
    warm_parser.add_argument(
        "--no-version-metadata",
        action="store_true",
        help="Disable metadata warming hints for the selected requests.",
    )
    _add_common_execution_args(warm_parser)

    index_parser = subparsers.add_parser(
        "index-all",
        help="Warm Maven coordinates from an inventory or expand package lists into all versions, optionally using sharding.",
    )
    index_source_group = index_parser.add_mutually_exclusive_group(required=True)
    index_source_group.add_argument(
        "--inventory",
        help="Inventory file in text, JSON, JSONL, or .gz form.",
    )
    index_source_group.add_argument(
        "--package-file",
        help="Text file containing one Maven package name (`groupId:artifactId`) per line.",
    )
    index_source_group.add_argument(
        "--package",
        action="append",
        dest="packages",
        default=[],
        help="Explicit Maven package name (`groupId:artifactId`). Can be repeated.",
    )
    index_parser.add_argument("--shard-index", type=int, default=0, help="Shard index to process.")
    index_parser.add_argument("--shard-count", type=int, default=1, help="Total number of shards.")
    index_parser.add_argument("--limit", type=int, help="Process only the first N planned coordinates for this shard.")
    index_parser.add_argument(
        "--sync-mode",
        choices=SYNC_MODES,
        default="incremental",
        help=(
            "Sync strategy: `incremental` repairs local gaps and adds new work, "
            "`new-only` trusts completed state entries, `repair-missing` focuses on local gaps, "
            "and `full` rescans the full source."
        ),
    )
    index_parser.add_argument(
        "--no-version-metadata",
        action="store_true",
        help="Disable metadata warming hints on planned requests. Package-list version discovery still fetches remote `maven-metadata.xml`.",
    )
    _add_common_execution_args(index_parser)

    return parser


def _build_batch_service() -> MavenBatchWarmService:
    return MavenBatchWarmService()


def _build_planner() -> MavenCrawlPlanner:
    return MavenCrawlPlanner()


def _emit(payload: dict[str, object], *, pretty: bool) -> None:
    if pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=False))


def _load_warm_requests(args) -> list:
    if args.manifest:
        if args.coordinates or args.coordinate or args.gavs or args.coordinate_file:
            raise ValueError("direct Maven coordinates cannot be used together with `--manifest`")
        return ManifestAdapter().load(args.manifest)
    return BuildRequestAdapter().from_cli_args(args)


def _warm_payload(summary, *, request_count: int) -> dict[str, object]:
    return {
        "command": "warm",
        "request_count": request_count,
        "summary": summary.to_dict(),
    }


def _index_payload(summary, *, plan) -> dict[str, object]:
    return {
        "command": "index-all",
        "plan": {
            "source_path": plan.source_path,
            "sync_mode": plan.sync_mode,
            "total_request_count": plan.total_request_count,
            "selected_request_count": plan.selected_request_count,
            "planned_request_count": plan.planned_request_count,
            "filtered_state_count": plan.filtered_state_count,
            "filtered_local_count": plan.filtered_local_count,
            "planning_failure_count": len(getattr(plan, "planning_failures", ()) or ()),
            "shard_index": plan.shard_index,
            "shard_count": plan.shard_count,
            "limit": plan.limit,
        },
        "summary": summary.to_dict(),
    }


def _planning_failure_items(plan) -> tuple[BatchWarmItemResult, ...]:
    failures = tuple(getattr(plan, "planning_failures", ()) or ())
    return tuple(
        BatchWarmItemResult(
            coordinate=failure.coordinate,
            status="error",
            stage=failure.stage,
            pom_path=None,
            pom_url=None,
            metadata_status="not-attempted",
            metadata_path=None,
            metadata_url=None,
            source_type=failure.source_type,
            source_path=failure.source_path,
            source_line=failure.source_line,
            warning_count=0,
            warning_codes=(),
            cleanup_removed_count=0,
            error_message=failure.error_message,
            failure=failure.to_dict(),
        )
        for failure in failures
    )


def _merge_index_summary(summary: BatchWarmSummary, *, plan, failure_log: str | None) -> BatchWarmSummary:
    planning_items = _planning_failure_items(plan)
    if not planning_items:
        return summary

    if failure_log:
        for item in planning_items:
            append_jsonl(failure_log, item.failure or {})

    merged_items = list(planning_items)
    merged_items.extend(summary.items)
    return BatchWarmSummary.from_items(merged_items)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    batch_service = _build_batch_service()

    if args.command == "warm":
        requests = _load_warm_requests(args)
        summary = batch_service.run(
            requests,
            repository_root=args.repository_root,
            skip_existing=args.skip_existing,
            fail_fast=args.fail_fast,
            failure_log=args.failure_log,
            state_file=args.state_file,
        )
        _emit(_warm_payload(summary, request_count=len(requests)), pretty=args.pretty)
        return 0 if summary.status != "error" else 1

    planner = _build_planner()
    if args.inventory:
        plan = planner.build_plan_from_inventory(
            args.inventory,
            include_version_metadata=not args.no_version_metadata,
            sync_mode=args.sync_mode,
            repository_root=args.repository_root,
            state_file=args.state_file,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            limit=args.limit,
        )
    elif args.package_file:
        plan = planner.build_plan_from_package_file(
            args.package_file,
            include_version_metadata=not args.no_version_metadata,
            sync_mode=args.sync_mode,
            repository_root=args.repository_root,
            state_file=args.state_file,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            limit=args.limit,
            fail_fast=args.fail_fast,
        )
    else:
        plan = planner.build_plan_from_packages(
            args.packages,
            include_version_metadata=not args.no_version_metadata,
            sync_mode=args.sync_mode,
            repository_root=args.repository_root,
            state_file=args.state_file,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            limit=args.limit,
            fail_fast=args.fail_fast,
        )
    if args.fail_fast and getattr(plan, "planning_failures", ()):
        summary = BatchWarmSummary.from_items(())
    else:
        summary = batch_service.run(
            plan,
            repository_root=args.repository_root,
            skip_existing=args.skip_existing,
            fail_fast=args.fail_fast,
            failure_log=args.failure_log,
            state_file=args.state_file,
            verify_completed_state=args.sync_mode in {"incremental", "repair-missing"},
        )
    combined_summary = _merge_index_summary(summary, plan=plan, failure_log=args.failure_log)
    _emit(_index_payload(combined_summary, plan=plan), pretty=args.pretty)
    return 0 if combined_summary.status != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
