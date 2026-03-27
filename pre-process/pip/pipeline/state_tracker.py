from __future__ import annotations

from pathlib import Path
import sys

try:
    from packaging.utils import canonicalize_name
except ImportError:  # pragma: no cover
    from pip._vendor.packaging.utils import canonicalize_name


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[3]
COMMON_UTILS_ROOT = PROJECT_ROOT / "pre-process" / "common" / "utils"

for path in (PROJECT_ROOT, COMMON_UTILS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from jsonl import append_jsonl, read_jsonl
from pip_models import utc_now_iso


StateKey = tuple[str, str]


def build_state_key(project_name: str | None, version: str | None) -> StateKey | None:
    if not project_name or not version:
        return None
    normalized_name = canonicalize_name(project_name)
    normalized_version = version.strip()
    if not normalized_name or not normalized_version:
        return None
    return normalized_name, normalized_version


def load_completed_keys(path: str | None) -> set[StateKey]:
    if not path:
        return set()
    completed: set[StateKey] = set()
    for entry in read_jsonl(path):
        state_status = str(entry.get("state_status") or "").strip().lower()
        if state_status not in {"completed", "skip-existing", "skipped-existing", "resume-skip"}:
            continue
        key = build_state_key(
            str(entry["project_name"]) if entry.get("project_name") else None,
            str(entry["version"]) if entry.get("version") else None,
        )
        if key is not None:
            completed.add(key)
    return completed


def append_state_entry(
    path: str | None,
    *,
    project_name: str | None,
    version: str | None,
    artifact_path: str | None,
    stage: str,
    state_status: str,
) -> None:
    if not path:
        return
    append_jsonl(
        path,
        {
            "project_name": project_name,
            "version": version,
            "artifact_path": artifact_path,
            "stage": stage,
            "state_status": state_status,
            "recorded_at": utc_now_iso(),
        },
    )


__all__ = ["StateKey", "append_state_entry", "build_state_key", "load_completed_keys"]
