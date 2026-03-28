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


from maven_models import MavenCoordinate
from loaders.repository_layout import build_repository_layout


@dataclass(frozen=True, slots=True)
class RepositoryCleanupResult:
    scope: str
    removed_paths: tuple[str, ...]

    @property
    def removed_count(self) -> int:
        return len(self.removed_paths)


def _remove_files(paths: list[Path]) -> tuple[str, ...]:
    removed: list[str] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if not path.exists() or not path.is_file():
            continue
        path.unlink()
        removed.append(str(path))
    return tuple(sorted(removed))


def cleanup_artifact_tracking_files(
    coordinate: MavenCoordinate | str,
    *,
    repository_root: str | None = None,
) -> RepositoryCleanupResult:
    layout = build_repository_layout(coordinate, repository_root=repository_root)
    artifact_dir = Path(layout.absolute_artifact_directory)
    candidates: list[Path] = [Path(layout.tracking_path)]
    if artifact_dir.exists():
        candidates.extend(sorted(artifact_dir.glob("*.lastUpdated")))
    return RepositoryCleanupResult(
        scope="artifact",
        removed_paths=_remove_files(candidates),
    )


def cleanup_metadata_tracking_files(
    coordinate: MavenCoordinate | str,
    *,
    repository_root: str | None = None,
) -> RepositoryCleanupResult:
    layout = build_repository_layout(coordinate, repository_root=repository_root)
    metadata_dir = Path(layout.metadata_path).parent
    candidates: list[Path] = []
    if metadata_dir.exists():
        candidates.extend(sorted(metadata_dir.glob("maven-metadata*.lastUpdated")))
        candidates.extend(sorted(metadata_dir.glob("resolver-status.properties")))
    return RepositoryCleanupResult(
        scope="metadata",
        removed_paths=_remove_files(candidates),
    )


__all__ = [
    "RepositoryCleanupResult",
    "cleanup_artifact_tracking_files",
    "cleanup_metadata_tracking_files",
]
