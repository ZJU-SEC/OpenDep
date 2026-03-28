from __future__ import annotations

import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[2]
COMMON_MODELS_ROOT = PROJECT_ROOT / "pre-process" / "common" / "models"

for path in (PROJECT_ROOT, COMMON_MODELS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from maven_records import (  # noqa: E402
    LocalRepositoryLayout,
    MavenCoordinate,
    WarmRequest,
)


__all__ = [
    "LocalRepositoryLayout",
    "MavenCoordinate",
    "WarmRequest",
]
