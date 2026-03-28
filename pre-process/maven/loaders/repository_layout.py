from __future__ import annotations

import os
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
MAVEN_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]

for path in (MAVEN_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from maven_models import LocalRepositoryLayout, MavenCoordinate


DEFAULT_REPOSITORY_ROOT = str((Path.home() / ".m2" / "repository").resolve())
REPOSITORY_ROOT_ENV = "MAVEN_PREPROCESS_REPOSITORY_ROOT"


def resolve_repository_root(repository_root: str | None = None) -> str:
    configured = repository_root or os.getenv(REPOSITORY_ROOT_ENV)
    if configured:
        return str(Path(configured).expanduser().resolve())
    return DEFAULT_REPOSITORY_ROOT


def build_repository_layout(
    coordinate: MavenCoordinate | str,
    *,
    repository_root: str | None = None,
) -> LocalRepositoryLayout:
    resolved_coordinate = (
        coordinate if isinstance(coordinate, MavenCoordinate) else MavenCoordinate.from_string(str(coordinate))
    )
    return LocalRepositoryLayout(
        repository_root=resolve_repository_root(repository_root),
        coordinate=resolved_coordinate,
    )


__all__ = [
    "DEFAULT_REPOSITORY_ROOT",
    "REPOSITORY_ROOT_ENV",
    "build_repository_layout",
    "resolve_repository_root",
]
