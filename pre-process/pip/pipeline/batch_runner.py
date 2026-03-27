from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
from typing import Iterable


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
COMMON_UTILS_ROOT = PROJECT_ROOT / "pre-process" / "common" / "utils"

for path in (PROJECT_ROOT, COMMON_UTILS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from jsonl import append_jsonl
from logging_utils import get_logger
from pip_models import BatchBuildItemResult, BatchBuildSummary, BuildJobSpec
from pipeline.extractor import PipDependencyExtractor
from pipeline.state_tracker import append_state_entry, build_state_key, load_completed_keys
from pipeline.validation import ExtractionQualityValidator, is_retryable_exception
from retry import RetrySettings, run_with_retry


class PipBatchJobRunner:
    def __init__(
        self,
        *,
        extractor=None,
        validator=None,
        loader=None,
        table_name: str | None = None,
        retry_settings: RetrySettings | None = None,
        logger=None,
    ) -> None:
        self._extractor = extractor or PipDependencyExtractor()
        self._validator = validator or ExtractionQualityValidator()
        self._loader = loader
        self._table_name = table_name or getattr(loader, "table_name", "unknown")
        self._retry_settings = retry_settings or RetrySettings.from_env()
        self._logger = logger or get_logger("preprocess.pip.batch")

    @property
    def loader(self):
        return self._loader

    def run(
        self,
        jobs: Iterable[BuildJobSpec],
        *,
        ensure_schema: bool = False,
        allow_legacy_fallback: bool = True,
        failure_log: str | None = None,
        fail_fast: bool = False,
        skip_existing: bool = False,
        state_file: str | None = None,
        resume_keys: set[tuple[str, str]] | None = None,
    ) -> BatchBuildSummary:
        job_list = list(jobs)
        item_results: list[BatchBuildItemResult] = []
        completed_keys = set(resume_keys or ())
        completed_keys.update(load_completed_keys(state_file))
        cleanup_refcounts: dict[str, int] = {}
        cleanup_blocked: set[str] = set()

        for job in job_list:
            if job.cleanup_artifact_path:
                cleanup_refcounts[job.cleanup_artifact_path] = cleanup_refcounts.get(job.cleanup_artifact_path, 0) + 1

        if ensure_schema and self._loader is not None:
            self._logger.info("Ensuring schema for table `%s`", self._table_name)
            run_with_retry(
                self._loader.ensure_schema,
                settings=self._retry_settings,
                retry_if=is_retryable_exception,
                on_retry=self._on_retry("ensure-schema", artifact_path=None),
            )

        self._logger.info("Starting batch run with %s job(s)", len(job_list))
        for index, job in enumerate(job_list, start=1):
            self._logger.info("Processing job %s/%s: %s", index, len(job_list), job.artifact_path)
            state_key = build_state_key(job.project_name, job.version)
            if state_key is not None and state_key in completed_keys:
                item_results.append(
                    BatchBuildItemResult(
                        artifact_path=job.artifact_path,
                        status="skipped",
                        stage="resume-skip",
                        name=job.project_name,
                        version=job.version,
                    )
                )
                self._logger.info("Skipping already completed job for %s==%s from state file", state_key[0], state_key[1])
                continue

            if skip_existing and self._loader is not None and state_key is not None and self._loader.has_release(*state_key):
                item_results.append(
                    BatchBuildItemResult(
                        artifact_path=job.artifact_path,
                        status="skipped",
                        stage="skip-existing",
                        name=job.project_name,
                        version=job.version,
                    )
                )
                append_state_entry(
                    state_file,
                    project_name=job.project_name,
                    version=job.version,
                    artifact_path=job.artifact_path,
                    stage="skip-existing",
                    state_status="skipped-existing",
                )
                completed_keys.add(state_key)
                self._logger.info("Skipping existing indexed release for %s==%s", state_key[0], state_key[1])
                continue

            try:
                extracted = run_with_retry(
                    lambda: self._extractor.extract_local_artifact(
                        job.artifact_path,
                        project_name=job.project_name,
                        version=job.version,
                        allow_legacy_fallback=allow_legacy_fallback,
                    ),
                    settings=self._retry_settings,
                    retry_if=is_retryable_exception,
                    on_retry=self._on_retry("extract", artifact_path=job.artifact_path),
                )
                if job.artifact_url is not None or job.artifact_hash is not None:
                    extracted = replace(
                        extracted,
                        artifact_url=job.artifact_url or extracted.artifact_url,
                        artifact_hash=job.artifact_hash or extracted.artifact_hash,
                    )
            except Exception as exc:
                failure = self._validator.build_failure(
                    artifact_path=job.artifact_path,
                    artifact_kind=None,
                    project_name=job.project_name,
                    version=job.version,
                    stage="extract",
                    exc=exc,
                )
                if failure_log:
                    append_jsonl(failure_log, failure.to_dict())
                self._block_cleanup(job, cleanup_blocked, cleanup_refcounts)
                item_results.append(
                    BatchBuildItemResult(
                        artifact_path=job.artifact_path,
                        status="error",
                        stage="extract",
                        failure=failure.to_dict(),
                    )
                )
                self._logger.error("Extraction failed for %s: %s", job.artifact_path, failure.error_message)
                if fail_fast:
                    break
                continue

            validation = self._validator.validate(extracted)
            if not validation.ok or validation.record is None:
                issue_messages = "; ".join(item.message for item in validation.errors) or "validation failed"
                failure = self._validator.build_failure(
                    artifact_path=extracted.artifact_path or job.artifact_path,
                    artifact_kind=extracted.artifact_kind,
                    project_name=extracted.name,
                    version=extracted.version,
                    stage="validate",
                    exc=ValueError(issue_messages),
                )
                if failure_log:
                    append_jsonl(failure_log, failure.to_dict())
                self._block_cleanup(job, cleanup_blocked, cleanup_refcounts)
                item_results.append(
                    BatchBuildItemResult(
                        artifact_path=job.artifact_path,
                        status="error",
                        stage="validate",
                        dependency_count=extracted.dependency_count,
                        name=extracted.name,
                        version=extracted.version,
                        source_kind=extracted.source_kind,
                        validation_status=validation.status,
                        warning_count=len(validation.warnings),
                        error_count=len(validation.errors),
                        failure=failure.to_dict(),
                    )
                )
                self._logger.error("Validation failed for %s: %s", job.artifact_path, failure.error_message)
                if fail_fast:
                    break
                continue

            try:
                if self._loader is not None:
                    run_with_retry(
                        lambda: self._loader.upsert_record(validation.record),
                        settings=self._retry_settings,
                        retry_if=is_retryable_exception,
                        on_retry=self._on_retry("load", artifact_path=job.artifact_path),
                    )
            except Exception as exc:
                failure = self._validator.build_failure(
                    artifact_path=validation.record.artifact_path or job.artifact_path,
                    artifact_kind=validation.record.artifact_kind,
                    project_name=validation.record.name,
                    version=validation.record.version,
                    stage="load",
                    exc=exc,
                )
                if failure_log:
                    append_jsonl(failure_log, failure.to_dict())
                self._block_cleanup(job, cleanup_blocked, cleanup_refcounts)
                item_results.append(
                    BatchBuildItemResult(
                        artifact_path=job.artifact_path,
                        status="error",
                        stage="load",
                        dependency_count=validation.record.dependency_count,
                        name=validation.record.name,
                        version=validation.record.version,
                        source_kind=validation.record.source_kind,
                        validation_status=validation.status,
                        warning_count=len(validation.warnings),
                        error_count=len(validation.errors),
                        failure=failure.to_dict(),
                    )
                )
                self._logger.error("Load failed for %s: %s", job.artifact_path, failure.error_message)
                if fail_fast:
                    break
                continue

            item_results.append(
                BatchBuildItemResult(
                    artifact_path=job.artifact_path,
                    status=validation.status,
                    stage="load",
                    dependency_count=validation.record.dependency_count,
                    name=validation.record.name,
                    version=validation.record.version,
                    source_kind=validation.record.source_kind,
                    validation_status=validation.status,
                    warning_count=len(validation.warnings),
                    error_count=len(validation.errors),
                )
            )
            success_key = build_state_key(validation.record.name, validation.record.version)
            append_state_entry(
                state_file,
                project_name=validation.record.name,
                version=validation.record.version,
                artifact_path=job.artifact_path,
                stage="load",
                state_status="completed",
            )
            if success_key is not None:
                completed_keys.add(success_key)
            if validation.status == "partial":
                self._logger.warning(
                    "Processed %s with warnings (%s warning(s))",
                    job.artifact_path,
                    len(validation.warnings),
                )
            self._cleanup_if_last_success(job, cleanup_refcounts, cleanup_blocked)

        status = "ok"
        if any(item.status == "error" for item in item_results):
            status = "partial" if any(item.status != "error" for item in item_results) else "error"
        elif any(item.status == "partial" for item in item_results):
            status = "partial"

        return BatchBuildSummary(
            status=status,
            items=tuple(item_results),
            ensure_schema=ensure_schema,
            table_name=self._table_name,
            failure_log=failure_log,
        )

    def _block_cleanup(
        self,
        job: BuildJobSpec,
        cleanup_blocked: set[str],
        cleanup_refcounts: dict[str, int],
    ) -> None:
        cleanup_path = job.cleanup_artifact_path
        if not cleanup_path:
            return
        cleanup_blocked.add(cleanup_path)
        if cleanup_path in cleanup_refcounts:
            cleanup_refcounts[cleanup_path] = max(cleanup_refcounts[cleanup_path] - 1, 0)

    def _cleanup_if_last_success(
        self,
        job: BuildJobSpec,
        cleanup_refcounts: dict[str, int],
        cleanup_blocked: set[str],
    ) -> None:
        cleanup_path = job.cleanup_artifact_path
        if not cleanup_path:
            return
        remaining = cleanup_refcounts.get(cleanup_path, 0)
        if remaining > 0:
            cleanup_refcounts[cleanup_path] = remaining - 1
        remaining = cleanup_refcounts.get(cleanup_path, 0)
        if remaining > 0 or cleanup_path in cleanup_blocked:
            return
        self._remove_artifact(cleanup_path)
        cleanup_refcounts.pop(cleanup_path, None)

    def _remove_artifact(self, artifact_path: str) -> None:
        path = Path(artifact_path)
        if not path.exists():
            return
        if not path.is_file():
            self._logger.warning("Skipping cleanup for non-file artifact path: %s", artifact_path)
            return
        path.unlink()
        self._logger.info("Removed downloaded artifact %s", artifact_path)

    def _on_retry(self, stage: str, *, artifact_path: str | None):
        def callback(attempt: int, exc: Exception, delay: float) -> None:
            if artifact_path:
                self._logger.warning(
                    "Retrying %s for %s after %s failure on attempt %s in %.2fs",
                    stage,
                    artifact_path,
                    exc.__class__.__name__,
                    attempt,
                    delay,
                )
            else:
                self._logger.warning(
                    "Retrying %s after %s failure on attempt %s in %.2fs",
                    stage,
                    exc.__class__.__name__,
                    attempt,
                    delay,
                )

        return callback
