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


from jsonl import append_jsonl
from logging_utils import get_logger
from loaders.postgres_loader import DEFAULT_SCHEMA_FILE, DEFAULT_TABLE_NAME, PipMetadataPostgresLoader
from pipeline.extractor import PipDependencyExtractor
from pipeline.validation import ExtractionQualityValidator, is_retryable_exception
from retry import RetrySettings, run_with_retry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pip-preprocess-load",
        description="Extract, validate, and optionally load pip dependency metadata into PostgreSQL.",
    )
    parser.add_argument("artifact", help="Path to a local wheel / sdist / egg artifact.")
    parser.add_argument("--name", help="Optional package name override.")
    parser.add_argument("--version", help="Optional package version override.")
    parser.add_argument("--dsn", help="Optional PostgreSQL DSN override.")
    parser.add_argument("--table", default=DEFAULT_TABLE_NAME, help="Destination table name.")
    parser.add_argument(
        "--failure-log",
        help="Optional JSONL file path used to persist extraction or validation failures.",
    )
    parser.add_argument(
        "--schema-file",
        help="Optional schema SQL file used with --ensure-schema.",
    )
    parser.add_argument(
        "--ensure-schema",
        action="store_true",
        help="Apply the pip schema SQL before writing records.",
    )
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    extractor = PipDependencyExtractor()
    validator = ExtractionQualityValidator()
    retry_settings = RetrySettings.from_env()
    logger = get_logger("preprocess.pip.load")
    loader = PipMetadataPostgresLoader(
        dsn=args.dsn,
        table_name=args.table,
        schema_file=args.schema_file or DEFAULT_SCHEMA_FILE,
    )

    try:
        try:
            logger.info("Extracting metadata from %s", args.artifact)
            extracted = run_with_retry(
                lambda: extractor.extract_local_artifact(
                    args.artifact,
                    project_name=args.name,
                    version=args.version,
                    allow_legacy_fallback=not args.no_legacy_fallback,
                ),
                settings=retry_settings,
                retry_if=is_retryable_exception,
                on_retry=lambda attempt, exc, delay: logger.warning(
                    "Retrying extract for %s after %s failure on attempt %s in %.2fs",
                    args.artifact,
                    exc.__class__.__name__,
                    attempt,
                    delay,
                ),
            )
        except Exception as exc:
            failure = validator.build_failure(
                artifact_path=args.artifact,
                artifact_kind=None,
                project_name=args.name,
                version=args.version,
                stage="extract",
                exc=exc,
            )
            if args.failure_log:
                append_jsonl(args.failure_log, failure.to_dict())
            _emit(
                {
                    "status": "error",
                    "stage": "extract",
                    "failure": failure.to_dict(),
                },
                pretty=args.pretty,
            )
            return 1

        validation = validator.validate(extracted)
        if not validation.ok or validation.record is None:
            issue_messages = "; ".join(item.message for item in validation.errors) or "validation failed"
            failure = validator.build_failure(
                artifact_path=extracted.artifact_path or args.artifact,
                artifact_kind=extracted.artifact_kind,
                project_name=extracted.name,
                version=extracted.version,
                stage="validate",
                exc=ValueError(issue_messages),
            )
            if args.failure_log:
                append_jsonl(args.failure_log, failure.to_dict())
            _emit(
                {
                    "status": "error",
                    "stage": "validate",
                    "validation": validation.to_dict(),
                    "failure": failure.to_dict(),
                },
                pretty=args.pretty,
            )
            return 1

        try:
            if args.ensure_schema:
                logger.info("Ensuring schema for table `%s`", loader.table_name)
                run_with_retry(
                    loader.ensure_schema,
                    settings=retry_settings,
                    retry_if=is_retryable_exception,
                    on_retry=lambda attempt, exc, delay: logger.warning(
                        "Retrying schema initialization after %s failure on attempt %s in %.2fs",
                        exc.__class__.__name__,
                        attempt,
                        delay,
                    ),
                )
            logger.info("Upserting %s==%s into `%s`", validation.record.name, validation.record.version, loader.table_name)
            run_with_retry(
                lambda: loader.upsert_record(validation.record),
                settings=retry_settings,
                retry_if=is_retryable_exception,
                on_retry=lambda attempt, exc, delay: logger.warning(
                    "Retrying load for %s after %s failure on attempt %s in %.2fs",
                    args.artifact,
                    exc.__class__.__name__,
                    attempt,
                    delay,
                ),
            )
        except Exception as exc:
            failure = validator.build_failure(
                artifact_path=validation.record.artifact_path or args.artifact,
                artifact_kind=validation.record.artifact_kind,
                project_name=validation.record.name,
                version=validation.record.version,
                stage="load",
                exc=exc,
            )
            if args.failure_log:
                append_jsonl(args.failure_log, failure.to_dict())
            _emit(
                {
                    "status": "error",
                    "stage": "load",
                    "validation": validation.to_dict(),
                    "failure": failure.to_dict(),
                    "store": {
                        "backend": "postgres",
                        "table": loader.table_name,
                    },
                },
                pretty=args.pretty,
            )
            return 1

        _emit(
            {
                "status": validation.status,
                "operation": "load",
                "validation": validation.to_dict(),
                "store": {
                    "backend": "postgres",
                    "table": loader.table_name,
                },
            },
            pretty=args.pretty,
        )
        return 0
    finally:
        loader.close()


if __name__ == "__main__":
    raise SystemExit(main())
