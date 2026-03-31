from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
CARGO_ROOT = CURRENT_FILE.parents[1]
DEFAULT_INDEX_URL = "https://github.com/rust-lang/crates.io-index.git"


def _resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


@dataclass(frozen=True)
class CargoDataLayout:
    data_root: Path
    index_dir: Path
    local_registry_dir: Path

    @classmethod
    def from_overrides(
        cls,
        *,
        data_root: str | None = None,
        index_dir: str | None = None,
        local_registry_dir: str | None = None,
    ) -> "CargoDataLayout":
        resolved_data_root = _resolve_path(
            data_root or os.getenv("CARGO_PREPROCESS_DATA_ROOT") or (CARGO_ROOT / "data")
        )
        resolved_index_dir = _resolve_path(
            index_dir or os.getenv("CARGO_PREPROCESS_INDEX_DIR") or (resolved_data_root / "crates.io-index")
        )
        resolved_local_registry_dir = _resolve_path(
            local_registry_dir
            or os.getenv("CARGO_PREPROCESS_LOCAL_REGISTRY_DIR")
            or (resolved_data_root / "local-registry")
        )
        return cls(
            data_root=resolved_data_root,
            index_dir=resolved_index_dir,
            local_registry_dir=resolved_local_registry_dir,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "data_root": str(self.data_root),
            "index_dir": str(self.index_dir),
            "local_registry_dir": str(self.local_registry_dir),
        }
