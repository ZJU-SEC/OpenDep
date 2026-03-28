from __future__ import annotations

from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
MAVEN_ROOT = CURRENT_FILE.parents[1]
PROJECT_ROOT = CURRENT_FILE.parents[3]

for path in (MAVEN_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from maven_models import MavenCoordinate, WarmRequest


def _load_coordinate_specs_file(coordinate_file: str) -> list[tuple[str, int]]:
    path = Path(coordinate_file).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"coordinate file does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"coordinate file is not a file: {path}")

    specs: list[tuple[str, int]] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("--"):
            raise ValueError(f"invalid Maven coordinate in file at line {line_number}: {stripped}")
        coordinate = MavenCoordinate.from_string(stripped).gav
        if coordinate in seen:
            continue
        seen.add(coordinate)
        specs.append((coordinate, line_number))

    if not specs:
        raise ValueError(f"coordinate file does not contain any Maven coordinates: {path}")
    return specs


def _extend_coordinate_values(target: list[str], raw_value) -> None:
    if raw_value is None:
        return
    if isinstance(raw_value, str):
        if raw_value.strip():
            target.append(raw_value.strip())
        return
    for item in raw_value:
        normalized = str(item).strip()
        if normalized:
            target.append(normalized)


class BuildRequestAdapter:
    def from_cli_args(self, args) -> list[WarmRequest]:
        include_version_metadata = not bool(getattr(args, "no_version_metadata", False))

        raw_coordinates: list[str] = []
        _extend_coordinate_values(raw_coordinates, getattr(args, "coordinates", None))
        _extend_coordinate_values(raw_coordinates, getattr(args, "coordinate", None))
        _extend_coordinate_values(raw_coordinates, getattr(args, "gavs", None))

        requests: list[WarmRequest] = []
        seen: set[str] = set()

        for raw_value in raw_coordinates:
            coordinate = MavenCoordinate.from_string(raw_value)
            if coordinate.gav in seen:
                continue
            seen.add(coordinate.gav)
            requests.append(
                WarmRequest(
                    coordinate=coordinate,
                    include_version_metadata=include_version_metadata,
                    source_type="explicit",
                )
            )

        coordinate_file = getattr(args, "coordinate_file", None)
        if coordinate_file:
            path = str(Path(coordinate_file).expanduser().resolve())
            for raw_value, line_number in _load_coordinate_specs_file(coordinate_file):
                coordinate = MavenCoordinate.from_string(raw_value)
                if coordinate.gav in seen:
                    continue
                seen.add(coordinate.gav)
                requests.append(
                    WarmRequest(
                        coordinate=coordinate,
                        include_version_metadata=include_version_metadata,
                        source_type="coordinate-file",
                        source_path=path,
                        source_line=line_number,
                    )
                )

        if not requests:
            raise ValueError("provide at least one Maven coordinate or `--coordinate-file`, or use `--manifest`")
        return requests


__all__ = ["BuildRequestAdapter"]
