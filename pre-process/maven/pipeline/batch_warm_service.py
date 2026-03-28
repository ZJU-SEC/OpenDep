from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Iterable


CURRENT_FILE = Path(__file__).resolve()
MAVEN_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]
COMMON_UTILS_ROOT = PROJECT_ROOT / "pre-process" / "common" / "utils"

for path in (MAVEN_ROOT, PROJECT_ROOT, COMMON_UTILS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from logging_utils import get_logger
from jsonl import append_jsonl
from maven_models import WarmRequest
from pipeline.crawl_planner import CrawlPlan
from pipeline.local_state import inspect_local_warm_state
from pipeline.state_tracker import append_state_entry, build_state_key, load_completed_keys
from pipeline.warm_service import MavenWarmService
from pipeline.validation import build_failure


@dataclass(frozen=True, slots=True)
class BatchWarmItemResult:
    coordinate: str
    status: str
    stage: str | None
    pom_path: str | None
    pom_url: str | None
    metadata_status: str
    metadata_path: str | None
    metadata_url: str | None
    source_type: str
    source_path: str | None
    source_line: int | None
    sequence: int | None = None
    shard_id: int | None = None
    warning_count: int = 0
    warning_codes: tuple[str, ...] = ()
    cleanup_removed_count: int = 0
    error_message: str | None = None
    warning_message: str | None = None
    metadata_error_message: str | None = None
    failure: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "coordinate": self.coordinate,
            "status": self.status,
            "stage": self.stage,
            "pom_path": self.pom_path,
            "pom_url": self.pom_url,
            "metadata_status": self.metadata_status,
            "metadata_path": self.metadata_path,
            "metadata_url": self.metadata_url,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "source_line": self.source_line,
            "sequence": self.sequence,
            "shard_id": self.shard_id,
            "warning_count": self.warning_count,
            "warning_codes": list(self.warning_codes),
            "cleanup_removed_count": self.cleanup_removed_count,
            "error_message": self.error_message,
            "warning_message": self.warning_message,
            "metadata_error_message": self.metadata_error_message,
            "failure": self.failure,
        }


@dataclass(frozen=True, slots=True)
class BatchWarmSummary:
    status: str
    total_items: int
    fetched_count: int
    updated_count: int
    skipped_count: int
    partial_count: int
    error_count: int
    warning_count: int
    items: tuple[BatchWarmItemResult, ...]

    @classmethod
    def from_items(cls, items: Iterable[BatchWarmItemResult]) -> "BatchWarmSummary":
        item_list = list(items)
        fetched_count = sum(1 for item in item_list if item.status == "fetched")
        updated_count = sum(1 for item in item_list if item.status == "updated")
        skipped_count = sum(1 for item in item_list if item.status == "skipped")
        partial_count = sum(1 for item in item_list if item.status == "partial")
        error_count = sum(1 for item in item_list if item.status == "error")
        warning_count = sum(item.warning_count for item in item_list)

        status = "ok"
        if error_count:
            status = "partial" if error_count < len(item_list) else "error"
        elif partial_count:
            status = "partial"

        return cls(
            status=status,
            total_items=len(item_list),
            fetched_count=fetched_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            partial_count=partial_count,
            error_count=error_count,
            warning_count=warning_count,
            items=tuple(item_list),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "total_items": self.total_items,
            "fetched_count": self.fetched_count,
            "updated_count": self.updated_count,
            "skipped_count": self.skipped_count,
            "partial_count": self.partial_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "items": [item.to_dict() for item in self.items],
        }


class MavenBatchWarmService:
    def __init__(
        self,
        *,
        warm_service: MavenWarmService | None = None,
        logger=None,
    ) -> None:
        self._warm_service = warm_service or MavenWarmService()
        self._logger = logger or get_logger("preprocess.maven.batch")

    def run(
        self,
        requests_or_plan: Iterable[WarmRequest] | CrawlPlan,
        *,
        repository_root: str | None = None,
        skip_existing: bool = False,
        fail_fast: bool = False,
        failure_log: str | None = None,
        state_file: str | None = None,
        verify_completed_state: bool = False,
    ) -> BatchWarmSummary:
        if isinstance(requests_or_plan, CrawlPlan):
            planned_items = list(requests_or_plan.items)
        else:
            planned_items = list(requests_or_plan)

        results: list[BatchWarmItemResult] = []
        completed_keys = load_completed_keys(state_file)
        for index, item in enumerate(planned_items, start=1):
            if isinstance(requests_or_plan, CrawlPlan):
                request = item.request
                sequence = item.sequence
                shard_id = item.shard_id
            else:
                request = item
                sequence = index
                shard_id = None

            state_key = build_state_key(request)
            if state_key in completed_keys:
                if verify_completed_state:
                    local_state = inspect_local_warm_state(request, repository_root=repository_root)
                    if local_state.can_verify and not local_state.is_satisfied:
                        self._logger.info(
                            "Reprocessing Maven job marked completed because local %s is %s: %s",
                            local_state.check_target,
                            local_state.reason,
                            request.request_key,
                        )
                    else:
                        result = BatchWarmItemResult(
                            coordinate=request.request_key,
                            status="skipped",
                            stage="resume-skip",
                            pom_path=None,
                            pom_url=None,
                            metadata_status="resume-skip",
                            metadata_path=None,
                            metadata_url=None,
                            source_type=request.source_type,
                            source_path=request.source_path,
                            source_line=request.source_line,
                            sequence=sequence,
                            shard_id=shard_id,
                            warning_count=0,
                            warning_codes=(),
                            cleanup_removed_count=0,
                        )
                        results.append(result)
                        append_state_entry(
                            state_file,
                            request=request,
                            stage="resume-skip",
                            state_status="resume-skip",
                            status="skipped",
                            pom_path=None,
                            metadata_path=None,
                            metadata_status="resume-skip",
                        )
                        self._logger.info("Skipping already completed Maven job from state file: %s", request.request_key)
                        continue
                else:
                    result = BatchWarmItemResult(
                        coordinate=request.request_key,
                        status="skipped",
                        stage="resume-skip",
                        pom_path=None,
                        pom_url=None,
                        metadata_status="resume-skip",
                        metadata_path=None,
                        metadata_url=None,
                        source_type=request.source_type,
                        source_path=request.source_path,
                        source_line=request.source_line,
                        sequence=sequence,
                        shard_id=shard_id,
                        warning_count=0,
                        warning_codes=(),
                        cleanup_removed_count=0,
                    )
                    results.append(result)
                    append_state_entry(
                        state_file,
                        request=request,
                        stage="resume-skip",
                        state_status="resume-skip",
                        status="skipped",
                        pom_path=None,
                        metadata_path=None,
                        metadata_status="resume-skip",
                    )
                    self._logger.info("Skipping already completed Maven job from state file: %s", request.request_key)
                    continue

            self._logger.info("Processing Maven warm job %s/%s: %s", index, len(planned_items), request.request_key)
            try:
                warm_result = self._warm_service.warm_request(
                    request,
                    repository_root=repository_root,
                    skip_existing=skip_existing,
                )
            except Exception as exc:
                results.append(
                    BatchWarmItemResult(
                        coordinate=request.request_key,
                        status="error",
                        stage="warm",
                        pom_path=None,
                        pom_url=None,
                        metadata_status="not-attempted",
                        metadata_path=None,
                        metadata_url=None,
                        source_type=request.source_type,
                        source_path=request.source_path,
                        source_line=request.source_line,
                        sequence=sequence,
                        shard_id=shard_id,
                        warning_count=0,
                        warning_codes=(),
                        cleanup_removed_count=0,
                        error_message=str(exc),
                        failure=build_failure(
                            request,
                            stage="warm",
                            exc=exc,
                        ).to_dict(),
                    )
                )
                self._logger.error("Failed to warm Maven POM for %s: %s", request.request_key, exc)
                if failure_log:
                    append_jsonl(failure_log, results[-1].failure or {})
                append_state_entry(
                    state_file,
                    request=request,
                    stage="warm",
                    state_status="error",
                    status="error",
                    pom_path=None,
                    metadata_path=None,
                    metadata_status="not-attempted",
                )
                if fail_fast:
                    break
                continue

            warning_codes = tuple(issue.code for issue in warm_result.warnings)
            failure_payload = warm_result.failure.to_dict() if warm_result.failure is not None else None
            results.append(
                BatchWarmItemResult(
                    coordinate=request.request_key,
                    status=warm_result.status,
                    stage=warm_result.failure.stage if warm_result.failure is not None else None,
                    pom_path=warm_result.pom_path,
                    pom_url=warm_result.pom_url,
                    metadata_status=warm_result.metadata_result.status,
                    metadata_path=warm_result.metadata_result.path,
                    metadata_url=warm_result.metadata_result.url,
                    source_type=request.source_type,
                    source_path=request.source_path,
                    source_line=request.source_line,
                    sequence=sequence,
                    shard_id=shard_id,
                    warning_count=len(warning_codes),
                    warning_codes=warning_codes,
                    cleanup_removed_count=warm_result.cleanup_result.removed_count if warm_result.cleanup_result else 0,
                    warning_message=warm_result.warning_message,
                    metadata_error_message=warm_result.metadata_result.error_message,
                    error_message=warm_result.failure.error_message if warm_result.failure is not None else None,
                    failure=failure_payload,
                )
            )
            result_item = results[-1]
            if failure_log and failure_payload is not None:
                append_jsonl(failure_log, failure_payload)
            state_status = "error"
            stage = result_item.stage or "warm"
            if warm_result.failure is None:
                state_status = "skipped-existing" if warm_result.status == "skipped" else "completed"
                completed_keys.add(state_key)
            append_state_entry(
                state_file,
                request=request,
                stage=stage,
                state_status=state_status,
                status=warm_result.status,
                pom_path=warm_result.pom_path,
                metadata_path=warm_result.metadata_result.path,
                metadata_status=warm_result.metadata_result.status,
            )
            if fail_fast and warm_result.status == "error":
                break

        return BatchWarmSummary.from_items(results)


__all__ = [
    "BatchWarmItemResult",
    "BatchWarmSummary",
    "MavenBatchWarmService",
]
