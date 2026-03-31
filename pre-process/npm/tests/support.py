from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
NPM_ROOT = PROJECT_ROOT / "pre-process" / "npm"
COMMON_DATABASE_ROOT = PROJECT_ROOT / "pre-process" / "common" / "database"

for path in (NPM_ROOT, PROJECT_ROOT, COMMON_DATABASE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
