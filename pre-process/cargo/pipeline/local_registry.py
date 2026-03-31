from __future__ import annotations

import shutil
from pathlib import Path


class LocalRegistryError(RuntimeError):
    """Raised when preparing a Cargo local-registry layout fails."""


def inspect_local_registry(path: Path) -> dict[str, object]:
    index_dir = path / "index"
    config_path = index_dir / "config.json"
    return {
        "path": str(path),
        "exists": path.exists(),
        "index_dir": str(index_dir),
        "index_exists": index_dir.exists(),
        "config_json": str(config_path),
        "config_json_exists": config_path.exists(),
    }


def stage_local_registry(index_dir: Path, local_registry_dir: Path, *, force: bool = False) -> dict[str, object]:
    if not index_dir.exists():
        raise LocalRegistryError(f"managed index directory does not exist: {index_dir}")
    if not (index_dir / "config.json").exists():
        raise LocalRegistryError(
            f"managed index directory does not look like a Cargo index clone: missing {index_dir / 'config.json'}"
        )

    if local_registry_dir.exists():
        if not force:
            raise LocalRegistryError(
                f"local-registry output already exists: {local_registry_dir}; rerun with --force to replace it"
            )
        shutil.rmtree(local_registry_dir)

    local_registry_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(index_dir, local_registry_dir / "index", ignore=shutil.ignore_patterns(".git"))
    return inspect_local_registry(local_registry_dir)
