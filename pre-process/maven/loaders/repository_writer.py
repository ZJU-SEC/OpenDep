from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
import tempfile


CURRENT_FILE = Path(__file__).resolve()
MAVEN_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]

for path in (MAVEN_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from maven_models import LocalRepositoryLayout, MavenCoordinate
from loaders.repository_layout import build_repository_layout


def _normalize_coordinate(coordinate: MavenCoordinate | str) -> MavenCoordinate:
    if isinstance(coordinate, MavenCoordinate):
        return coordinate
    return MavenCoordinate.from_string(str(coordinate))


def _normalize_payload(pom_payload: bytes | str) -> bytes:
    if isinstance(pom_payload, bytes):
        payload = pom_payload
    else:
        payload = pom_payload.encode("utf-8")
    if not payload:
        raise ValueError("pom_payload cannot be empty")
    return payload


@dataclass(frozen=True, slots=True)
class RepositoryWriteResult:
    layout: LocalRepositoryLayout
    bytes_written: int
    existed_before_write: bool


def pom_exists(
    coordinate: MavenCoordinate | str,
    *,
    repository_root: str | None = None,
) -> bool:
    layout = build_repository_layout(coordinate, repository_root=repository_root)
    pom_path = Path(layout.pom_path)
    return pom_path.exists() and pom_path.is_file() and pom_path.stat().st_size > 0


def metadata_exists(
    coordinate: MavenCoordinate | str,
    *,
    repository_root: str | None = None,
) -> bool:
    layout = build_repository_layout(coordinate, repository_root=repository_root)
    metadata_path = Path(layout.metadata_path)
    return metadata_path.exists() and metadata_path.is_file() and metadata_path.stat().st_size > 0


def _write_path(path: Path, payload: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existed_before_write = path.exists()

    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as temp_file:
            temp_file.write(payload)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_path = temp_file.name
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass
        raise
    return existed_before_write


def write_pom_file(
    coordinate: MavenCoordinate | str,
    pom_payload: bytes | str,
    *,
    repository_root: str | None = None,
) -> RepositoryWriteResult:
    layout = build_repository_layout(coordinate, repository_root=repository_root)
    payload = _normalize_payload(pom_payload)
    target_path = Path(layout.pom_path)
    existed_before_write = _write_path(target_path, payload)

    return RepositoryWriteResult(
        layout=layout,
        bytes_written=len(payload),
        existed_before_write=existed_before_write,
    )


def write_metadata_file(
    coordinate: MavenCoordinate | str,
    metadata_payload: bytes | str,
    *,
    repository_root: str | None = None,
) -> RepositoryWriteResult:
    layout = build_repository_layout(coordinate, repository_root=repository_root)
    payload = _normalize_payload(metadata_payload)
    target_path = Path(layout.metadata_path)
    existed_before_write = _write_path(target_path, payload)

    return RepositoryWriteResult(
        layout=layout,
        bytes_written=len(payload),
        existed_before_write=existed_before_write,
    )


__all__ = [
    "RepositoryWriteResult",
    "metadata_exists",
    "pom_exists",
    "write_metadata_file",
    "write_pom_file",
]
