from __future__ import annotations

from dataclasses import dataclass

try:
    from pip._internal.models.wheel import Wheel as PipWheel
except ImportError:  # pragma: no cover - pip is expected in runtime images
    PipWheel = None

from resolving.containerization.images.pip.backend.inspectors.archive import detect_artifact_kind


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    filename: str
    url: str | None = None
    packagetype: str | None = None
    python_version: str | None = None
    requires_python: str | None = None
    yanked: bool = False
    hashes: dict[str, str] | None = None

    @property
    def kind(self) -> str:
        return detect_artifact_kind(self.filename)

    @property
    def supported(self) -> bool:
        return self.kind in {"wheel", "sdist"}

    @classmethod
    def from_pypi_file(cls, item: dict[str, object]) -> "ArtifactReference":
        return cls(
            filename=str(item.get("filename") or item.get("url") or ""),
            url=str(item["url"]) if item.get("url") else None,
            packagetype=str(item["packagetype"]) if item.get("packagetype") else None,
            python_version=str(item["python_version"]) if item.get("python_version") else None,
            requires_python=str(item["requires_python"]) if item.get("requires_python") else None,
            yanked=bool(item.get("yanked", False)),
            hashes=dict(item["digests"]) if isinstance(item.get("digests"), dict) else None,
        )


def _wheel_python_rank(filename: str) -> int:
    if PipWheel is None:
        return 3
    try:
        wheel = PipWheel(filename)
    except Exception:
        return 3
    file_tags = tuple(getattr(wheel, "file_tags", ()) or ())
    if file_tags:
        interpreters = {getattr(tag, "interpreter", None) for tag in file_tags}
        if interpreters & {"py2.py3", "py3"}:
            return 1
        if interpreters & {"py2", "py"}:
            return 2
        return 2

    pyversions = getattr(wheel, "pyversions", None)
    if pyversions in (["py2.py3"], ["py3"], ["any"]):
        return 1
    return 2


def _wheel_platform_rank(filename: str) -> int:
    if PipWheel is None:
        return 3
    try:
        wheel = PipWheel(filename)
    except Exception:
        return 3
    file_tags = tuple(getattr(wheel, "file_tags", ()) or ())
    if file_tags:
        platforms = {getattr(tag, "platform", None) for tag in file_tags}
        if platforms & {"any", "linux_x86_64"}:
            return 1
        return 2

    plats = getattr(wheel, "plats", None) or ()
    if "any" in plats or "linux_x86_64" in plats:
        return 1
    return 2


def _artifact_sort_key(artifact: ArtifactReference) -> tuple[int, int, int, str]:
    if artifact.kind == "wheel":
        return (1, _wheel_python_rank(artifact.filename), _wheel_platform_rank(artifact.filename), artifact.filename)
    if artifact.filename.endswith(".tar.gz"):
        return (2, 3, 3, artifact.filename)
    if artifact.kind == "sdist":
        return (3, 3, 3, artifact.filename)
    return (9, 9, 9, artifact.filename)


def select_preferred_artifacts(artifacts: list[ArtifactReference]) -> list[ArtifactReference]:
    supported = [artifact for artifact in artifacts if artifact.supported]
    return sorted(supported, key=_artifact_sort_key)
