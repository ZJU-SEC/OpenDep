from __future__ import annotations

from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
MAVEN_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]
COMMON_UTILS_ROOT = PROJECT_ROOT / "pre-process" / "common" / "utils"

for path in (MAVEN_ROOT, PROJECT_ROOT, COMMON_UTILS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from jsonl import append_jsonl, read_jsonl
from maven_models import MavenCoordinate, WarmRequest
from pipeline.validation import utc_now_iso


StateKey = str
COMPLETED_STATE_STATUSES = frozenset({"completed", "skipped-existing", "resume-skip"})


def build_state_key(request_or_coordinate: WarmRequest | MavenCoordinate | str) -> StateKey:
    if isinstance(request_or_coordinate, WarmRequest):
        return request_or_coordinate.request_key
    if isinstance(request_or_coordinate, MavenCoordinate):
        return request_or_coordinate.gav
    return MavenCoordinate.from_string(str(request_or_coordinate)).gav


def load_latest_state_map(path: str | None) -> dict[StateKey, dict[str, object]]:
    if not path:
        return {}
    latest: dict[StateKey, dict[str, object]] = {}
    for entry in read_jsonl(path):
        coordinate = str(entry.get("coordinate") or "").strip()
        if coordinate:
            latest[coordinate] = entry
    return latest


def load_completed_keys(path: str | None) -> set[StateKey]:
    completed: set[StateKey] = set()
    for coordinate, entry in load_latest_state_map(path).items():
        state_status = str(entry.get("state_status") or "").strip().lower()
        if state_status in COMPLETED_STATE_STATUSES:
            completed.add(coordinate)
    return completed


def append_state_entry(
    path: str | None,
    *,
    request: WarmRequest,
    stage: str,
    state_status: str,
    status: str,
    pom_path: str | None,
    metadata_path: str | None,
    metadata_status: str | None,
) -> None:
    if not path:
        return
    append_jsonl(
        path,
        {
            "coordinate": request.request_key,
            "ga": request.coordinate.ga,
            "version": request.coordinate.version,
            "stage": stage,
            "state_status": state_status,
            "status": status,
            "pom_path": pom_path,
            "metadata_path": metadata_path,
            "metadata_status": metadata_status,
            "source_type": request.source_type,
            "source_path": request.source_path,
            "source_line": request.source_line,
            "recorded_at": utc_now_iso(),
        },
    )


__all__ = [
    "COMPLETED_STATE_STATUSES",
    "StateKey",
    "append_state_entry",
    "build_state_key",
    "load_completed_keys",
    "load_latest_state_map",
]
