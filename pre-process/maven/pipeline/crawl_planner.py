from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import sys
from typing import Iterable


CURRENT_FILE = Path(__file__).resolve()
MAVEN_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]

for path in (MAVEN_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from maven_models import WarmRequest
from adapters.inventory import InventoryAdapter
from adapters.package_list import PackageListAdapter, build_package_specs
from pipeline.local_state import inspect_local_warm_state
from pipeline.package_version_planner import MavenPackageVersionPlanner
from pipeline.validation import WarmFailureRecord
from pipeline.state_tracker import load_completed_keys


SYNC_MODES = ("full", "incremental", "new-only", "repair-missing")


def _stable_shard_id(request_key: str, shard_count: int) -> int:
    digest = hashlib.sha1(request_key.encode("utf-8")).hexdigest()
    return int(digest, 16) % shard_count


def _dedupe_requests(requests: Iterable[WarmRequest]) -> list[WarmRequest]:
    deduped: dict[str, WarmRequest] = {}
    for request in requests:
        deduped.setdefault(request.request_key, request)
    return [deduped[key] for key in sorted(deduped)]


def normalize_sync_mode(sync_mode: str | None) -> str:
    normalized = "full" if sync_mode is None else str(sync_mode).strip().lower()
    if normalized not in SYNC_MODES:
        raise ValueError(f"invalid sync_mode `{sync_mode}`; expected one of {', '.join(SYNC_MODES)}")
    return normalized


def _select_requests_for_sync(
    requests: Iterable[WarmRequest],
    *,
    sync_mode: str,
    repository_root: str | None,
    state_file: str | None,
) -> tuple[list[WarmRequest], int, int]:
    normalized_sync_mode = normalize_sync_mode(sync_mode)
    deduped_requests = _dedupe_requests(requests)
    if normalized_sync_mode == "full":
        return deduped_requests, 0, 0

    completed_keys = load_completed_keys(state_file)
    selected_requests: list[WarmRequest] = []
    filtered_state_count = 0
    filtered_local_count = 0

    for request in deduped_requests:
        completed_in_state = request.request_key in completed_keys
        inspection = inspect_local_warm_state(request, repository_root=repository_root)
        locally_satisfied = inspection.can_verify and inspection.is_satisfied

        if normalized_sync_mode == "new-only":
            if completed_in_state:
                filtered_state_count += 1
                continue
            if locally_satisfied:
                filtered_local_count += 1
                continue
            selected_requests.append(request)
            continue

        if normalized_sync_mode == "repair-missing":
            if locally_satisfied:
                filtered_local_count += 1
                continue
            if not inspection.can_verify and completed_in_state:
                filtered_state_count += 1
                continue
            selected_requests.append(request)
            continue

        if locally_satisfied:
            filtered_local_count += 1
            continue
        if not inspection.can_verify and completed_in_state:
            filtered_state_count += 1
            continue
        selected_requests.append(request)

    return selected_requests, filtered_state_count, filtered_local_count


@dataclass(frozen=True, slots=True)
class CrawlPlanItem:
    sequence: int
    shard_id: int
    request: WarmRequest


@dataclass(frozen=True, slots=True)
class CrawlPlan:
    items: tuple[CrawlPlanItem, ...]
    total_request_count: int
    selected_request_count: int
    planned_request_count: int
    shard_index: int
    shard_count: int
    limit: int | None = None
    source_path: str | None = None
    sync_mode: str = "full"
    filtered_state_count: int = 0
    filtered_local_count: int = 0
    planning_failures: tuple[WarmFailureRecord, ...] = ()

    @property
    def requests(self) -> tuple[WarmRequest, ...]:
        return tuple(item.request for item in self.items)


class MavenCrawlPlanner:
    def __init__(
        self,
        *,
        inventory_adapter: InventoryAdapter | None = None,
        package_list_adapter: PackageListAdapter | None = None,
        package_version_planner: MavenPackageVersionPlanner | None = None,
    ) -> None:
        self._inventory_adapter = inventory_adapter or InventoryAdapter()
        self._package_list_adapter = package_list_adapter or PackageListAdapter()
        self._package_version_planner = package_version_planner or MavenPackageVersionPlanner()

    def build_plan(
        self,
        requests: Iterable[WarmRequest],
        *,
        shard_index: int = 0,
        shard_count: int = 1,
        limit: int | None = None,
        source_path: str | None = None,
        total_request_count: int | None = None,
        sync_mode: str = "full",
        filtered_state_count: int = 0,
        filtered_local_count: int = 0,
        planning_failures: tuple[WarmFailureRecord, ...] = (),
    ) -> CrawlPlan:
        normalized_sync_mode = normalize_sync_mode(sync_mode)
        if shard_count <= 0:
            raise ValueError("shard_count must be positive")
        if shard_index < 0 or shard_index >= shard_count:
            raise ValueError("shard_index must be within [0, shard_count)")
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive when provided")

        deduped_requests = _dedupe_requests(requests)
        selected_requests: list[tuple[int, WarmRequest]] = []
        for request in deduped_requests:
            shard_id = _stable_shard_id(request.request_key, shard_count)
            if shard_id != shard_index:
                continue
            selected_requests.append((shard_id, request))

        if limit is not None:
            selected_requests = selected_requests[:limit]

        items = tuple(
            CrawlPlanItem(
                sequence=index,
                shard_id=shard_id,
                request=request,
            )
            for index, (shard_id, request) in enumerate(selected_requests, start=1)
        )
        return CrawlPlan(
            items=items,
            total_request_count=total_request_count or len(deduped_requests),
            selected_request_count=len(deduped_requests),
            planned_request_count=len(items),
            shard_index=shard_index,
            shard_count=shard_count,
            limit=limit,
            source_path=source_path,
            sync_mode=normalized_sync_mode,
            filtered_state_count=filtered_state_count,
            filtered_local_count=filtered_local_count,
            planning_failures=planning_failures,
        )

    def build_plan_from_inventory(
        self,
        inventory_path: str,
        *,
        include_version_metadata: bool = True,
        sync_mode: str = "full",
        repository_root: str | None = None,
        state_file: str | None = None,
        shard_index: int = 0,
        shard_count: int = 1,
        limit: int | None = None,
    ) -> CrawlPlan:
        resolved_path = str(Path(inventory_path).expanduser().resolve())
        requests = self._inventory_adapter.load(
            resolved_path,
            include_version_metadata=include_version_metadata,
        )
        deduped_request_count = len(_dedupe_requests(requests))
        selected_requests, filtered_state_count, filtered_local_count = _select_requests_for_sync(
            requests,
            sync_mode=sync_mode,
            repository_root=repository_root,
            state_file=state_file,
        )
        return self.build_plan(
            selected_requests,
            shard_index=shard_index,
            shard_count=shard_count,
            limit=limit,
            source_path=resolved_path,
            total_request_count=deduped_request_count,
            sync_mode=sync_mode,
            filtered_state_count=filtered_state_count,
            filtered_local_count=filtered_local_count,
        )

    def build_plan_from_package_file(
        self,
        package_file: str,
        *,
        include_version_metadata: bool = True,
        sync_mode: str = "full",
        repository_root: str | None = None,
        state_file: str | None = None,
        shard_index: int = 0,
        shard_count: int = 1,
        limit: int | None = None,
        fail_fast: bool = False,
    ) -> CrawlPlan:
        resolved_path = str(Path(package_file).expanduser().resolve())
        packages = self._package_list_adapter.load(resolved_path)
        planning_result = self._package_version_planner.plan_all(
            packages,
            include_version_metadata=include_version_metadata,
            fail_fast=fail_fast,
        )
        requests = list(planning_result.requests)
        deduped_request_count = len(_dedupe_requests(requests))
        selected_requests, filtered_state_count, filtered_local_count = _select_requests_for_sync(
            requests,
            sync_mode=sync_mode,
            repository_root=repository_root,
            state_file=state_file,
        )
        return self.build_plan(
            selected_requests,
            shard_index=shard_index,
            shard_count=shard_count,
            limit=limit,
            source_path=resolved_path,
            total_request_count=deduped_request_count,
            sync_mode=sync_mode,
            filtered_state_count=filtered_state_count,
            filtered_local_count=filtered_local_count,
            planning_failures=planning_result.failures,
        )

    def build_plan_from_packages(
        self,
        packages,
        *,
        include_version_metadata: bool = True,
        sync_mode: str = "full",
        repository_root: str | None = None,
        state_file: str | None = None,
        shard_index: int = 0,
        shard_count: int = 1,
        limit: int | None = None,
        fail_fast: bool = False,
    ) -> CrawlPlan:
        package_specs = build_package_specs(packages)
        planning_result = self._package_version_planner.plan_all(
            package_specs,
            include_version_metadata=include_version_metadata,
            fail_fast=fail_fast,
        )
        requests = list(planning_result.requests)
        deduped_request_count = len(_dedupe_requests(requests))
        selected_requests, filtered_state_count, filtered_local_count = _select_requests_for_sync(
            requests,
            sync_mode=sync_mode,
            repository_root=repository_root,
            state_file=state_file,
        )
        return self.build_plan(
            selected_requests,
            shard_index=shard_index,
            shard_count=shard_count,
            limit=limit,
            source_path=None,
            total_request_count=deduped_request_count,
            sync_mode=sync_mode,
            filtered_state_count=filtered_state_count,
            filtered_local_count=filtered_local_count,
            planning_failures=planning_result.failures,
        )


__all__ = [
    "CrawlPlan",
    "CrawlPlanItem",
    "MavenCrawlPlanner",
    "SYNC_MODES",
    "normalize_sync_mode",
]
