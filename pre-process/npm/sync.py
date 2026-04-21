from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any


CURRENT_FILE = Path(__file__).resolve()
NPM_ROOT = CURRENT_FILE.parent
PROJECT_ROOT = CURRENT_FILE.parents[2]
COMMON_DATABASE_ROOT = PROJECT_ROOT / "pre-process" / "common" / "database"

for path in (NPM_ROOT, PROJECT_ROOT, COMMON_DATABASE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from adapters.changes_client import (
    DEFAULT_CHANGES_URL,
    DEFAULT_SYNC_REGISTRY_BASE_URL,
    NpmChangeEvent,
    NpmChangesClient,
)
from adapters.registry_client import NpmRegistryClient, NpmRegistryClientError
from loaders.postgres_loader import (
    DEFAULT_SCHEMA_FILE,
    DEFAULT_SYNC_STATE_SCHEMA_FILE,
    DEFAULT_SYNC_STATE_TABLE_NAME,
    DEFAULT_TABLE_NAME,
    DEFAULT_TOMBSTONE_SCHEMA_FILE,
    DEFAULT_TOMBSTONE_TABLE_NAME,
    NpmPackumentPostgresLoader,
    NpmSyncStatePostgresLoader,
    NpmTombstonePostgresLoader,
)
from pipeline.records import NpmPackumentRecord, NpmSyncCheckpointRecord, NpmTombstoneRecord


logger = logging.getLogger("npm_preprocess_sync")


@dataclass(frozen=True, slots=True)
class SyncRunOutcome:
    exit_code: int
    payload: dict[str, object]
    retryable: bool = False


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative number")
    return parsed


def _add_common_sync_args(parser: argparse.ArgumentParser, *, default_concurrency: int) -> None:
    parser.add_argument("--source-key", required=True, help="Logical checkpoint key for the npm source.")
    parser.add_argument("--dsn", help="Optional PostgreSQL DSN override.")
    parser.add_argument("--metadata-table", default=DEFAULT_TABLE_NAME, help="Destination metadata table name.")
    parser.add_argument(
        "--sync-state-table",
        default=DEFAULT_SYNC_STATE_TABLE_NAME,
        help="Destination checkpoint table name.",
    )
    parser.add_argument(
        "--tombstone-table",
        default=DEFAULT_TOMBSTONE_TABLE_NAME,
        help="Destination tombstone table name.",
    )
    parser.add_argument("--metadata-schema-file", help="Optional metadata schema SQL file used with --ensure-schema.")
    parser.add_argument(
        "--sync-state-schema-file",
        help="Optional sync-state schema SQL file used with --ensure-schema.",
    )
    parser.add_argument(
        "--tombstone-schema-file",
        help="Optional tombstone schema SQL file used with --ensure-schema.",
    )
    parser.add_argument(
        "--ensure-schema",
        action="store_true",
        help="Apply the metadata and sync-state schema SQL before reading or writing records.",
    )
    parser.add_argument(
        "--changes-url",
        default=DEFAULT_CHANGES_URL,
        help="Base URL of the npm _changes feed.",
    )
    parser.add_argument(
        "--registry-base-url",
        default=DEFAULT_SYNC_REGISTRY_BASE_URL,
        help="Base URL used to fetch packuments referenced by the _changes batch.",
    )
    parser.add_argument(
        "--since",
        help="Explicit _changes checkpoint token. When omitted, resume from npm_sync_state.last_seq.",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=1000,
        help="Maximum number of _changes rows to fetch in one batch.",
    )
    parser.add_argument(
        "--concurrency",
        type=_positive_int,
        default=default_concurrency,
        help="Maximum number of concurrent packument fetches for one batch.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output JSON.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="npm-preprocess-sync",
        description="Consume npm _changes batches and store them in PostgreSQL.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_once = subparsers.add_parser(
        "sync-once",
        help="Consume a single npm _changes batch and persist the result.",
    )
    _add_common_sync_args(sync_once, default_concurrency=1)

    sync_follow = subparsers.add_parser(
        "sync-follow",
        help="Continuously poll the npm _changes feed and persist batches.",
    )
    _add_common_sync_args(sync_follow, default_concurrency=4)
    sync_follow.add_argument(
        "--poll-interval",
        type=_positive_float,
        default=30.0,
        help="Seconds to wait after a non-idle successful batch.",
    )
    sync_follow.add_argument(
        "--idle-backoff",
        type=_positive_float,
        default=60.0,
        help="Seconds to wait after an idle poll or retryable batch failure.",
    )
    return parser


def _emit(payload: dict[str, object], *, pretty: bool) -> None:
    if pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=False))


def _status_from_counts(*, updated: int, skipped: int, deleted: int, errors: int) -> str:
    if errors == 0:
        return "ok"
    if updated > 0 or skipped > 0 or deleted > 0:
        return "partial"
    return "error"


def deduplicate_events(events: list[NpmChangeEvent]) -> list[NpmChangeEvent]:
    deduplicated: dict[str, NpmChangeEvent] = {}
    for event in events:
        if event.package_name in deduplicated:
            deduplicated.pop(event.package_name)
        deduplicated[event.package_name] = event
    return list(deduplicated.values())


def _record_from_event(registry_client: NpmRegistryClient, event: NpmChangeEvent) -> NpmPackumentRecord:
    download = registry_client.fetch_raw_packument(event.package_name)
    return NpmPackumentRecord.from_raw_packument(
        name=download.name,
        raw_packument=download.raw_packument,
        source_url=download.source_url,
        fetched_at=download.fetched_at,
        source_rev=download.source_rev or event.changes_rev,
    )


def _append_missing_packument_tombstone(
    *,
    tombstone_triplets: list[tuple[int, dict[str, object], NpmTombstoneRecord]],
    item: dict[str, object],
    index: int,
    event: NpmChangeEvent,
) -> None:
    item["status"] = "delete_pending"
    item["reason"] = "packument_not_found"
    tombstone_triplets.append(
        (
            index,
            item,
            NpmTombstoneRecord(
                name=event.package_name,
                source_rev=event.changes_rev,
                deleted_seq=event.sequence,
                deleted_at=datetime.now(timezone.utc),
            ),
        )
    )


def _build_preflight_error_payload(
    *,
    source_key: str,
    metadata_table: str,
    sync_state_table: str,
    tombstone_table: str,
    missing_tables: list[str],
) -> dict[str, object]:
    return {
        "status": "error",
        "operation": "sync-once",
        "source_key": source_key,
        "message": (
            "destination table(s) do not exist: "
            + ", ".join(f"`{name}`" for name in missing_tables)
            + "; rerun with `--ensure-schema` or apply the schema manually"
        ),
        "summary": {
            "fetched_package_count": 0,
            "updated_row_count": 0,
            "skipped_row_count": 0,
            "delete_event_count": 0,
            "error_count": 1,
            "checkpoint_advanced": False,
        },
        "store": {
            "backend": "postgres",
            "metadata_table": metadata_table,
            "sync_state_table": sync_state_table,
            "tombstone_table": tombstone_table,
        },
        "warnings": [],
        "results": [],
    }


def _build_batch_fetch_error_payload(
    *,
    source_key: str,
    metadata_table: str,
    sync_state_table: str,
    tombstone_table: str,
    changes_url: str,
    registry_base_url: str,
    since: str | None,
    limit: int,
    message: str,
) -> dict[str, object]:
    return {
        "status": "error",
        "operation": "sync-once",
        "source_key": source_key,
        "message": message,
        "summary": {
            "fetched_package_count": 0,
            "updated_row_count": 0,
            "skipped_row_count": 0,
            "delete_event_count": 0,
            "error_count": 1,
            "checkpoint_advanced": False,
        },
        "store": {
            "backend": "postgres",
            "metadata_table": metadata_table,
            "sync_state_table": sync_state_table,
            "tombstone_table": tombstone_table,
        },
        "source": {
            "changes_url": changes_url,
            "registry_base_url": registry_base_url,
            "since": since,
            "last_seq": None,
            "limit": limit,
        },
        "warnings": ["checkpoint was not advanced because the changes batch could not be fetched"],
        "results": [],
    }


def _process_batch_events(
    *,
    events: list[NpmChangeEvent],
    metadata_loader: NpmPackumentPostgresLoader,
    registry_client: NpmRegistryClient,
    concurrency: int,
) -> dict[str, object]:
    results: list[dict[str, object]] = []
    pending_fetches: list[tuple[int, dict[str, object], NpmChangeEvent, str | None]] = []
    tombstone_triplets: list[tuple[int, dict[str, object], NpmTombstoneRecord]] = []
    skipped_count = 0
    delete_count = 0
    error_count = 0
    fetched_count = 0
    fetched_triplets: list[tuple[int, dict[str, object], NpmPackumentRecord]] = []

    for event in events:
        item: dict[str, object] = {
            "name": event.package_name,
            "sequence": event.sequence,
            "changes_rev": event.changes_rev,
            "deleted": event.deleted,
        }
        results.append(item)

        if event.deleted:
            item["status"] = "delete_pending"
            delete_count += 1
            tombstone_triplets.append(
                (
                    len(results) - 1,
                    item,
                    NpmTombstoneRecord(
                        name=event.package_name,
                        source_rev=event.changes_rev,
                        deleted_seq=event.sequence,
                        deleted_at=datetime.now(timezone.utc),
                    ),
                )
            )
            continue

        existing_source_rev = metadata_loader.get_package_source_rev(event.package_name)
        if existing_source_rev and event.changes_rev and existing_source_rev == event.changes_rev:
            item["status"] = "skipped"
            item["reason"] = "source_rev_unchanged"
            skipped_count += 1
            continue

        pending_fetches.append((len(results) - 1, item, event, existing_source_rev))

    def handle_fetched_record(
        index: int,
        item: dict[str, object],
        existing_source_rev: str | None,
        record: NpmPackumentRecord,
    ) -> None:
        nonlocal fetched_count, skipped_count
        if existing_source_rev and record.source_rev and existing_source_rev == record.source_rev:
            item.update(record.to_dict())
            item["status"] = "skipped"
            item["reason"] = "source_rev_unchanged"
            skipped_count += 1
            return

        item.update(record.to_dict())
        item["status"] = "fetched"
        fetched_count += 1
        fetched_triplets.append((index, item, record))

    if concurrency <= 1:
        for index, item, event, existing_source_rev in pending_fetches:
            try:
                record = _record_from_event(registry_client, event)
            except NpmRegistryClientError as exc:
                if exc.status_code == 404:
                    _append_missing_packument_tombstone(
                        tombstone_triplets=tombstone_triplets,
                        item=item,
                        index=index,
                        event=event,
                    )
                    delete_count += 1
                    continue
                item["status"] = "error"
                item["error"] = str(exc)
                error_count += 1
                continue
            except Exception as exc:
                item["status"] = "error"
                item["error"] = str(exc)
                error_count += 1
                continue
            handle_fetched_record(index, item, existing_source_rev, record)
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_to_context = {
                executor.submit(_record_from_event, registry_client, event): (index, item, event, existing_source_rev)
                for index, item, event, existing_source_rev in pending_fetches
            }
            for future in as_completed(future_to_context):
                index, item, event, existing_source_rev = future_to_context[future]
                try:
                    record = future.result()
                except NpmRegistryClientError as exc:
                    if exc.status_code == 404:
                        _append_missing_packument_tombstone(
                            tombstone_triplets=tombstone_triplets,
                            item=item,
                            index=index,
                            event=event,
                        )
                        delete_count += 1
                        continue
                    item["status"] = "error"
                    item["error"] = str(exc)
                    error_count += 1
                    continue
                except Exception as exc:
                    item["status"] = "error"
                    item["error"] = str(exc)
                    error_count += 1
                    continue
                handle_fetched_record(index, item, existing_source_rev, record)

    fetched_triplets.sort(key=lambda entry: entry[0])
    tombstone_triplets.sort(key=lambda entry: entry[0])
    return {
        "results": results,
        "records_to_store": [record for _, _, record in fetched_triplets],
        "fetched_items": [item for _, item, _ in fetched_triplets],
        "tombstones_to_store": [tombstone for _, _, tombstone in tombstone_triplets],
        "delete_items": [item for _, item, _ in tombstone_triplets],
        "fetched_count": fetched_count,
        "skipped_count": skipped_count,
        "delete_count": delete_count,
        "error_count": error_count,
    }


def run_sync_once_command(args: argparse.Namespace) -> SyncRunOutcome:
    changes_client = NpmChangesClient(changes_url=args.changes_url)
    registry_client = NpmRegistryClient(base_url=args.registry_base_url)
    metadata_loader = NpmPackumentPostgresLoader(
        dsn=args.dsn,
        table_name=args.metadata_table,
        schema_file=args.metadata_schema_file or DEFAULT_SCHEMA_FILE,
    )
    sync_state_loader = NpmSyncStatePostgresLoader(
        dsn=args.dsn,
        table_name=args.sync_state_table,
        schema_file=args.sync_state_schema_file or DEFAULT_SYNC_STATE_SCHEMA_FILE,
    )
    tombstone_loader = NpmTombstonePostgresLoader(
        dsn=args.dsn,
        table_name=args.tombstone_table,
        schema_file=args.tombstone_schema_file or DEFAULT_TOMBSTONE_SCHEMA_FILE,
    )

    warnings: list[str] = []
    fetched_count = 0
    updated_count = 0
    skipped_count = 0
    delete_count = 0
    error_count = 0
    checkpoint_advanced = False
    since_token = args.since

    try:
        if args.ensure_schema:
            metadata_loader.ensure_schema()
            sync_state_loader.ensure_schema()
            tombstone_loader.ensure_schema()

        metadata_table_exists = metadata_loader.table_exists()
        sync_state_table_exists = sync_state_loader.table_exists()
        tombstone_table_exists = tombstone_loader.table_exists()
        if not metadata_table_exists or not sync_state_table_exists or not tombstone_table_exists:
            missing_tables: list[str] = []
            if not metadata_table_exists:
                missing_tables.append(metadata_loader.table_name)
            if not sync_state_table_exists:
                missing_tables.append(sync_state_loader.table_name)
            if not tombstone_table_exists:
                missing_tables.append(tombstone_loader.table_name)
            return SyncRunOutcome(
                exit_code=1,
                payload=_build_preflight_error_payload(
                    source_key=args.source_key,
                    metadata_table=metadata_loader.table_name,
                    sync_state_table=sync_state_loader.table_name,
                    tombstone_table=tombstone_loader.table_name,
                    missing_tables=missing_tables,
                ),
                retryable=False,
            )

        existing_checkpoint = sync_state_loader.get_checkpoint(args.source_key)
        if since_token is None and existing_checkpoint is not None:
            since_token = existing_checkpoint.last_seq

        try:
            batch = changes_client.fetch_changes_batch(since=since_token, limit=args.limit)
        except Exception as exc:
            return SyncRunOutcome(
                exit_code=1,
                payload=_build_batch_fetch_error_payload(
                    source_key=args.source_key,
                    metadata_table=metadata_loader.table_name,
                    sync_state_table=sync_state_loader.table_name,
                    tombstone_table=tombstone_loader.table_name,
                    changes_url=changes_client.changes_url,
                    registry_base_url=registry_client.base_url,
                    since=since_token,
                    limit=args.limit,
                    message=str(exc),
                ),
                retryable=True,
            )

        deduplicated_events = deduplicate_events(batch.events)
        processed = _process_batch_events(
            events=deduplicated_events,
            metadata_loader=metadata_loader,
            registry_client=registry_client,
            concurrency=getattr(args, "concurrency", 1),
        )

        results = processed["results"]
        records_to_store = processed["records_to_store"]
        fetched_items = processed["fetched_items"]
        tombstones_to_store = processed["tombstones_to_store"]
        delete_items = processed["delete_items"]
        fetched_count = int(processed["fetched_count"])
        skipped_count = int(processed["skipped_count"])
        delete_count = int(processed["delete_count"])
        error_count = int(processed["error_count"])

        if error_count == 0:
            next_last_seq = batch.last_seq if batch.last_seq is not None else since_token
            checkpoint = NpmSyncCheckpointRecord(
                source_key=args.source_key,
                registry_base_url=registry_client.base_url,
                changes_url=changes_client.changes_url,
                last_seq=next_last_seq,
                checkpointed_at=datetime.now(timezone.utc),
            )
            try:
                metadata_loader.apply_sync_batch(
                    records=records_to_store,
                    tombstones=tombstones_to_store,
                    checkpoint=checkpoint,
                    sync_state_loader=sync_state_loader,
                    tombstone_loader=tombstone_loader,
                )
                checkpoint_advanced = True
                updated_count = len(records_to_store)
                for item in fetched_items:
                    item["status"] = "updated"
                for item in delete_items:
                    item["status"] = "deleted"
            except Exception as exc:
                error_count += 1
                warnings.append("checkpoint was not advanced because batch persistence failed")
                for item in fetched_items:
                    item["status"] = "error"
                    item["error"] = f"batch persistence failed: {exc}"
                for item in delete_items:
                    item["status"] = "error"
                    item["error"] = f"batch persistence failed: {exc}"
        else:
            warnings.append("checkpoint was not advanced because one or more packument fetches failed")
            for item in delete_items:
                item["status"] = "error"
                item["error"] = "batch was not persisted because another packument fetch failed"

        payload = {
            "status": _status_from_counts(
                updated=updated_count,
                skipped=skipped_count,
                deleted=delete_count,
                errors=error_count,
            ),
            "operation": "sync-once",
            "source_key": args.source_key,
            "input_count": len(batch.events),
            "requested_count": len(deduplicated_events),
            "summary": {
                "fetched_package_count": fetched_count,
                "updated_row_count": updated_count,
                "skipped_row_count": skipped_count,
                "delete_event_count": delete_count,
                "error_count": error_count,
                "checkpoint_advanced": checkpoint_advanced,
            },
            "store": {
                "backend": "postgres",
                "metadata_table": metadata_loader.table_name,
                "sync_state_table": sync_state_loader.table_name,
                "tombstone_table": tombstone_loader.table_name,
            },
            "source": {
                "changes_url": changes_client.changes_url,
                "registry_base_url": registry_client.base_url,
                "since": since_token,
                "last_seq": batch.last_seq,
                "limit": args.limit,
                "concurrency": getattr(args, "concurrency", 1),
            },
            "warnings": warnings,
            "results": results,
        }
        return SyncRunOutcome(exit_code=0 if error_count == 0 else 1, payload=payload, retryable=error_count > 0)
    finally:
        metadata_loader.close()
        sync_state_loader.close()
        tombstone_loader.close()


def _configure_follow_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def run_sync_follow_command(args: argparse.Namespace) -> SyncRunOutcome:
    _configure_follow_logging()

    processed_batches = 0
    advanced_checkpoints = 0
    idle_polls = 0
    transient_failures = 0
    total_fetched = 0
    total_updated = 0
    total_skipped = 0
    total_deleted = 0
    last_batch_payload: dict[str, object] | None = None
    warnings: list[str] = []

    try:
        while True:
            outcome = run_sync_once_command(args)
            processed_batches += 1
            last_batch_payload = outcome.payload

            summary = outcome.payload.get("summary") if isinstance(outcome.payload.get("summary"), dict) else {}
            fetched_count = int(summary.get("fetched_package_count", 0) or 0)
            updated_count = int(summary.get("updated_row_count", 0) or 0)
            skipped_count = int(summary.get("skipped_row_count", 0) or 0)
            deleted_count = int(summary.get("delete_event_count", 0) or 0)
            checkpoint_advanced = bool(summary.get("checkpoint_advanced"))

            total_fetched += fetched_count
            total_updated += updated_count
            total_skipped += skipped_count
            total_deleted += deleted_count
            if checkpoint_advanced:
                advanced_checkpoints += 1

            is_idle = outcome.exit_code == 0 and updated_count == 0 and skipped_count == 0 and deleted_count == 0
            if is_idle:
                idle_polls += 1
                logger.info(
                    "idle poll for source_key=%s last_seq=%s",
                    args.source_key,
                    outcome.payload.get("source", {}).get("last_seq") if isinstance(outcome.payload.get("source"), dict) else None,
                )
                time.sleep(args.idle_backoff)
                continue

            if outcome.exit_code == 0:
                logger.info(
                    "processed batch for source_key=%s updated=%s skipped=%s deleted=%s checkpoint_advanced=%s",
                    args.source_key,
                    updated_count,
                    skipped_count,
                    deleted_count,
                    checkpoint_advanced,
                )
                time.sleep(args.poll_interval)
                continue

            if not outcome.retryable:
                warnings.append("sync-follow stopped due to non-retryable batch failure")
                payload = {
                    "status": "error",
                    "operation": "sync-follow",
                    "source_key": args.source_key,
                    "message": outcome.payload.get("message", "sync-follow stopped due to non-retryable error"),
                    "summary": {
                        "processed_batch_count": processed_batches,
                        "advanced_checkpoint_count": advanced_checkpoints,
                        "idle_poll_count": idle_polls,
                        "transient_failure_count": transient_failures,
                        "fetched_package_count": total_fetched,
                        "updated_row_count": total_updated,
                        "skipped_row_count": total_skipped,
                        "delete_event_count": total_deleted,
                    },
                    "source": {
                        "changes_url": args.changes_url,
                        "registry_base_url": args.registry_base_url,
                        "limit": args.limit,
                        "concurrency": args.concurrency,
                        "poll_interval": args.poll_interval,
                        "idle_backoff": args.idle_backoff,
                    },
                    "warnings": warnings,
                    "last_batch": last_batch_payload,
                }
                return SyncRunOutcome(exit_code=1, payload=payload, retryable=False)

            transient_failures += 1
            logger.warning(
                "retryable batch failure for source_key=%s message=%s",
                args.source_key,
                outcome.payload.get("message", "unknown error"),
            )
            time.sleep(args.idle_backoff)
    except KeyboardInterrupt:
        warnings.append("sync-follow stopped gracefully after interrupt")
        payload = {
            "status": "ok",
            "operation": "sync-follow",
            "source_key": args.source_key,
            "summary": {
                "processed_batch_count": processed_batches,
                "advanced_checkpoint_count": advanced_checkpoints,
                "idle_poll_count": idle_polls,
                "transient_failure_count": transient_failures,
                "fetched_package_count": total_fetched,
                "updated_row_count": total_updated,
                "skipped_row_count": total_skipped,
                "delete_event_count": total_deleted,
            },
            "source": {
                "changes_url": args.changes_url,
                "registry_base_url": args.registry_base_url,
                "limit": args.limit,
                "concurrency": args.concurrency,
                "poll_interval": args.poll_interval,
                "idle_backoff": args.idle_backoff,
            },
            "warnings": warnings,
            "last_batch": last_batch_payload,
        }
        return SyncRunOutcome(exit_code=0, payload=payload, retryable=False)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "sync-once":
        outcome = run_sync_once_command(args)
        _emit(outcome.payload, pretty=args.pretty)
        return outcome.exit_code

    if args.command == "sync-follow":
        outcome = run_sync_follow_command(args)
        _emit(outcome.payload, pretty=args.pretty)
        return outcome.exit_code

    raise ValueError(f"unsupported npm sync command `{args.command}`")


if __name__ == "__main__":
    raise SystemExit(main())
