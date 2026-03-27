from __future__ import annotations

from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
COMMON_UTILS_ROOT = PROJECT_ROOT / "pre-process" / "common" / "utils"

for path in (PROJECT_ROOT, COMMON_UTILS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from logging_utils import get_logger
from jsonl import append_jsonl
from pip_models import BatchBuildItemResult, BatchBuildSummary, BuildJobSpec, BuildRequest
from adapters.local_artifact import LocalArtifactAdapter
from pipeline.artifact_fetcher import ArtifactFetcher
from pipeline.batch_runner import PipBatchJobRunner
from pipeline.pypi_client import PyPIJsonClient
from pipeline.state_tracker import append_state_entry, build_state_key, load_completed_keys
from pipeline.validation import ExtractionQualityValidator
from pipeline.version_planner import VersionPlanner


class PipBuildService:
    def __init__(
        self,
        *,
        batch_runner: PipBatchJobRunner | None = None,
        version_planner=None,
        artifact_fetcher=None,
        validator=None,
        cache_dir: str | None = None,
        pypi_json_base_url: str = "https://pypi.org/pypi",
        http_user_agent: str = "OpenDep-Pip-preprocess/0.1",
        retry_settings=None,
        table_name: str = "unknown",
        logger=None,
    ) -> None:
        self._logger = logger or get_logger("preprocess.pip.build")
        self._validator = validator or ExtractionQualityValidator()
        self._artifact_adapter = LocalArtifactAdapter()
        if batch_runner is None:
            batch_runner = PipBatchJobRunner(table_name=table_name, retry_settings=retry_settings, logger=self._logger)
        self._batch_runner = batch_runner

        if version_planner is None or artifact_fetcher is None:
            client = PyPIJsonClient(
                cache_dir=cache_dir,
                pypi_json_base_url=pypi_json_base_url,
                http_user_agent=http_user_agent,
                retry_settings=retry_settings,
                logger=self._logger,
            )
            version_planner = version_planner or VersionPlanner(client)
            artifact_fetcher = artifact_fetcher or ArtifactFetcher(
                client,
                cache_dir=cache_dir,
                http_user_agent=http_user_agent,
                retry_settings=retry_settings,
                logger=self._logger,
            )

        self._version_planner = version_planner
        self._artifact_fetcher = artifact_fetcher
        self._table_name = table_name

    def run(
        self,
        requests: list[BuildRequest],
        *,
        ensure_schema: bool = False,
        allow_legacy_fallback: bool = True,
        failure_log: str | None = None,
        fail_fast: bool = False,
        skip_existing: bool = False,
        backfill: bool = False,
        state_file: str | None = None,
        cleanup_downloaded_artifacts: bool = False,
    ) -> BatchBuildSummary:
        jobs: list[BuildJobSpec] = []
        preflight_items: list[BatchBuildItemResult] = []
        should_abort = False
        effective_skip_existing = skip_existing or backfill
        completed_keys = load_completed_keys(state_file)
        loader = self._batch_runner.loader

        for request in requests:
            if request.is_artifact:
                try:
                    prepared = self._artifact_adapter.prepare_job(
                        request.artifact_path or "",
                        project_name=request.project_name,
                        version=request.versions[0] if len(request.versions) == 1 else None,
                    )
                except Exception as exc:
                    self._record_failure(preflight_items, request, stage="prepare", exc=exc, failure_log=failure_log)
                    if fail_fast:
                        should_abort = True
                        break
                    continue

                state_key = build_state_key(prepared.project_name, prepared.version)
                if self._should_skip_from_state(state_key, completed_keys):
                    self._record_skip(
                        preflight_items,
                        state_file=state_file,
                        artifact_path=prepared.artifact_path,
                        project_name=prepared.project_name,
                        version=prepared.version,
                        stage="resume-skip",
                        completed_keys=completed_keys,
                        state_key=state_key,
                    )
                    continue
                if effective_skip_existing and loader is not None and state_key is not None and loader.has_release(*state_key):
                    self._record_skip(
                        preflight_items,
                        state_file=state_file,
                        artifact_path=prepared.artifact_path,
                        project_name=prepared.project_name,
                        version=prepared.version,
                        stage="skip-existing",
                        completed_keys=completed_keys,
                        state_key=state_key,
                    )
                    continue

                jobs.append(
                    BuildJobSpec(
                        artifact_path=prepared.artifact_path,
                        project_name=prepared.project_name,
                        version=prepared.version,
                    )
                )
                continue

            if not request.is_package or not request.project_name:
                self._record_failure(
                    preflight_items,
                    request,
                    stage="plan",
                    exc=ValueError("unsupported build request"),
                    failure_log=failure_log,
                )
                if fail_fast:
                    should_abort = True
                    break
                continue

            try:
                planned_versions = self._version_planner.plan(request)
            except Exception as exc:
                self._record_failure(preflight_items, request, stage="plan", exc=exc, failure_log=failure_log)
                if fail_fast:
                    should_abort = True
                    break
                continue

            for planned in planned_versions:
                state_key = build_state_key(planned.project_name, planned.version)
                if self._should_skip_from_state(state_key, completed_keys):
                    self._record_skip(
                        preflight_items,
                        state_file=state_file,
                        artifact_path=None,
                        project_name=planned.project_name,
                        version=planned.version,
                        stage="resume-skip",
                        completed_keys=completed_keys,
                        state_key=state_key,
                    )
                    continue
                if effective_skip_existing and loader is not None and state_key is not None and loader.has_release(*state_key):
                    self._record_skip(
                        preflight_items,
                        state_file=state_file,
                        artifact_path=None,
                        project_name=planned.project_name,
                        version=planned.version,
                        stage="skip-existing",
                        completed_keys=completed_keys,
                        state_key=state_key,
                    )
                    continue
                try:
                    acquired = self._artifact_fetcher.acquire(
                        planned.project_name,
                        planned.version,
                        mirror_dir=request.mirror_dir,
                        cleanup_downloaded_artifacts=cleanup_downloaded_artifacts,
                    )
                except Exception as exc:
                    self._record_failure(
                        preflight_items,
                        request,
                        stage="acquire",
                        version=planned.version,
                        exc=exc,
                        failure_log=failure_log,
                    )
                    if fail_fast:
                        should_abort = True
                        break
                    continue
                jobs.append(acquired.to_build_job())

            if should_abort:
                break

        runner_summary = None
        if jobs and not should_abort:
            runner_summary = self._batch_runner.run(
                jobs,
                ensure_schema=ensure_schema,
                allow_legacy_fallback=allow_legacy_fallback,
                failure_log=failure_log,
                fail_fast=fail_fast,
                skip_existing=effective_skip_existing,
                state_file=state_file,
                resume_keys=completed_keys,
            )

        items = list(preflight_items)
        if runner_summary is not None:
            items.extend(runner_summary.items)

        status = "ok"
        if any(item.status == "error" for item in items):
            status = "partial" if any(item.status != "error" for item in items) else "error"
        elif any(item.status == "partial" for item in items):
            status = "partial"

        return BatchBuildSummary(
            status=status,
            items=tuple(items),
            ensure_schema=ensure_schema,
            table_name=self._table_name,
            failure_log=failure_log,
        )

    def _failure_item(
        self,
        request: BuildRequest,
        *,
        stage: str,
        exc: Exception,
        version: str | None = None,
    ) -> BatchBuildItemResult:
        failure = self._validator.build_failure(
            artifact_path=request.artifact_path or self._request_identity(request.project_name, version),
            artifact_kind=None,
            project_name=request.project_name,
            version=version or (request.versions[0] if len(request.versions) == 1 else None),
            stage=stage,
            exc=exc,
        )
        return BatchBuildItemResult(
            artifact_path=request.artifact_path,
            status="error",
            stage=stage,
            name=request.project_name,
            version=version or (request.versions[0] if len(request.versions) == 1 else None),
            failure=failure.to_dict(),
        )

    def _record_failure(
        self,
        items: list[BatchBuildItemResult],
        request: BuildRequest,
        *,
        stage: str,
        exc: Exception,
        failure_log: str | None,
        version: str | None = None,
    ) -> None:
        item = self._failure_item(request, stage=stage, exc=exc, version=version)
        items.append(item)
        if failure_log and item.failure is not None:
            append_jsonl(failure_log, item.failure)

    def _should_skip_from_state(
        self,
        state_key: tuple[str, str] | None,
        completed_keys: set[tuple[str, str]],
    ) -> bool:
        return state_key is not None and state_key in completed_keys

    def _record_skip(
        self,
        items: list[BatchBuildItemResult],
        *,
        state_file: str | None,
        artifact_path: str | None,
        project_name: str | None,
        version: str | None,
        stage: str,
        completed_keys: set[tuple[str, str]],
        state_key: tuple[str, str] | None,
    ) -> None:
        state_status = "skipped-existing" if stage == "skip-existing" else "resume-skip"
        items.append(
            BatchBuildItemResult(
                artifact_path=artifact_path,
                status="skipped",
                stage=stage,
                name=project_name,
                version=version,
            )
        )
        append_state_entry(
            state_file,
            project_name=project_name,
            version=version,
            artifact_path=artifact_path,
            stage=stage,
            state_status=state_status,
        )
        if state_key is not None:
            completed_keys.add(state_key)

    def _request_identity(self, project_name: str | None, version: str | None) -> str:
        if project_name and version:
            return f"request:{project_name}=={version}"
        if project_name:
            return f"request:{project_name}"
        return "request:unknown"


__all__ = ["PipBuildService"]
