from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
MAVEN_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]

for path in (MAVEN_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from maven_models import MavenCoordinate, WarmRequest
from loaders.repository_layout import build_repository_layout
from loaders.repository_writer import metadata_exists, pom_exists
from pipeline.validation import validate_metadata_payload, validate_pom_payload
from pipeline.version_metadata import build_version_metadata_plan


def _normalize_request(request: WarmRequest | MavenCoordinate | str) -> WarmRequest:
    if isinstance(request, WarmRequest):
        return request
    coordinate = request if isinstance(request, MavenCoordinate) else MavenCoordinate.from_string(str(request))
    return WarmRequest(coordinate=coordinate)


def _read_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


@dataclass(frozen=True, slots=True)
class LocalWarmInspection:
    request: WarmRequest
    check_target: str
    metadata_strategy: str
    can_verify: bool
    is_satisfied: bool
    exists: bool
    valid: bool
    path: str | None
    reason: str


def inspect_local_warm_state(
    request: WarmRequest | MavenCoordinate | str,
    *,
    repository_root: str | None = None,
) -> LocalWarmInspection:
    resolved_request = _normalize_request(request)
    layout = build_repository_layout(resolved_request.coordinate, repository_root=repository_root)
    metadata_plan = build_version_metadata_plan(
        resolved_request.coordinate.version,
        include_version_metadata=resolved_request.include_version_metadata,
    )

    if metadata_plan.direct_pom_fetch:
        if not pom_exists(resolved_request.coordinate, repository_root=layout.repository_root):
            return LocalWarmInspection(
                request=resolved_request,
                check_target="pom",
                metadata_strategy=metadata_plan.strategy,
                can_verify=True,
                is_satisfied=False,
                exists=False,
                valid=False,
                path=layout.pom_path,
                reason="missing-pom",
            )
        try:
            validate_pom_payload(_read_bytes(layout.pom_path))
        except Exception:
            return LocalWarmInspection(
                request=resolved_request,
                check_target="pom",
                metadata_strategy=metadata_plan.strategy,
                can_verify=True,
                is_satisfied=False,
                exists=True,
                valid=False,
                path=layout.pom_path,
                reason="invalid-pom",
            )
        return LocalWarmInspection(
            request=resolved_request,
            check_target="pom",
            metadata_strategy=metadata_plan.strategy,
            can_verify=True,
            is_satisfied=True,
            exists=True,
            valid=True,
            path=layout.pom_path,
            reason="ready",
        )

    if metadata_plan.supported:
        if not metadata_exists(resolved_request.coordinate, repository_root=layout.repository_root):
            return LocalWarmInspection(
                request=resolved_request,
                check_target="metadata",
                metadata_strategy=metadata_plan.strategy,
                can_verify=True,
                is_satisfied=False,
                exists=False,
                valid=False,
                path=layout.metadata_path,
                reason="missing-metadata",
            )
        try:
            validate_metadata_payload(_read_bytes(layout.metadata_path))
        except Exception:
            return LocalWarmInspection(
                request=resolved_request,
                check_target="metadata",
                metadata_strategy=metadata_plan.strategy,
                can_verify=True,
                is_satisfied=False,
                exists=True,
                valid=False,
                path=layout.metadata_path,
                reason="invalid-metadata",
            )
        return LocalWarmInspection(
            request=resolved_request,
            check_target="metadata",
            metadata_strategy=metadata_plan.strategy,
            can_verify=True,
            is_satisfied=True,
            exists=True,
            valid=True,
            path=layout.metadata_path,
            reason="ready",
        )

    return LocalWarmInspection(
        request=resolved_request,
        check_target="state-only",
        metadata_strategy=metadata_plan.strategy,
        can_verify=False,
        is_satisfied=False,
        exists=False,
        valid=False,
        path=None,
        reason=metadata_plan.reason,
    )


__all__ = [
    "LocalWarmInspection",
    "inspect_local_warm_state",
]
