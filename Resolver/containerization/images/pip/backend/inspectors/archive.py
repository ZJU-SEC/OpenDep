from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tarfile
import zipfile

try:
    from pip._internal.models.wheel import Wheel as PipWheel
except ImportError:  # pragma: no cover - pip is expected in runtime images
    PipWheel = None


SDIST_SUFFIXES = (".tar.gz", ".zip", ".tgz", ".tar.bz2", ".tar.xz")


def strip_known_archive_suffix(filename: str) -> str:
    for suffix in (".whl",) + SDIST_SUFFIXES:
        if filename.endswith(suffix):
            return filename[: -len(suffix)]
    return filename


def detect_artifact_kind(filename: str) -> str:
    if filename.endswith(".whl"):
        return "wheel"
    if filename.endswith(SDIST_SUFFIXES):
        return "sdist"
    return "unknown"


def is_supported_distribution(filename: str) -> bool:
    return detect_artifact_kind(filename) in {"wheel", "sdist"}


def infer_name_version_from_filename(filename: str) -> tuple[str | None, str | None]:
    basename = Path(filename).name
    if basename.endswith(".whl") and PipWheel is not None:
        try:
            wheel = PipWheel(basename)
            return wheel.name, wheel.version
        except Exception:
            pass

    stripped = strip_known_archive_suffix(basename)
    if "-" not in stripped:
        return None, None
    name, version = stripped.rsplit("-", 1)
    return name or None, version or None


@dataclass(slots=True)
class ArchiveEntry:
    name: str

    @property
    def basename(self) -> str:
        return Path(self.name).name

    @property
    def depth(self) -> int:
        return self.name.count("/")


class DistributionArchive:
    def __init__(self, artifact_path: str) -> None:
        self.artifact_path = artifact_path
        self.kind = detect_artifact_kind(artifact_path)
        self._archive = None
        self._entries: list[ArchiveEntry] = []

    def __enter__(self) -> "DistributionArchive":
        if zipfile.is_zipfile(self.artifact_path):
            self._archive = zipfile.ZipFile(self.artifact_path)
            self._entries = [ArchiveEntry(name) for name in self._archive.namelist()]
            return self

        if tarfile.is_tarfile(self.artifact_path):
            self._archive = tarfile.open(self.artifact_path, "r:*")
            self._entries = [ArchiveEntry(name) for name in self._archive.getnames()]
            return self

        raise ValueError(f"unsupported distribution archive: {self.artifact_path}")

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._archive is not None:
            self._archive.close()
        self._archive = None

    @property
    def entries(self) -> list[ArchiveEntry]:
        return list(self._entries)

    @property
    def names(self) -> list[str]:
        return [entry.name for entry in self._entries]

    def read_bytes(self, name: str) -> bytes:
        if isinstance(self._archive, zipfile.ZipFile):
            return self._archive.read(name)
        if isinstance(self._archive, tarfile.TarFile):
            member = self._archive.extractfile(name)
            if member is None:
                raise FileNotFoundError(name)
            return member.read()
        raise RuntimeError("archive is not open")

    def read_text(self, name: str, encoding: str = "utf-8") -> str:
        return self.read_bytes(name).decode(encoding, errors="ignore")

    def find_first(
        self,
        *,
        suffix: str | None = None,
        basename: str | None = None,
    ) -> str | None:
        candidates = self._entries
        if suffix is not None:
            candidates = [entry for entry in candidates if entry.name.endswith(suffix)]
        if basename is not None:
            candidates = [entry for entry in candidates if entry.basename == basename]
        if not candidates:
            return None
        candidates.sort(key=lambda entry: (entry.depth, entry.name))
        return candidates[0].name


def open_distribution_archive(artifact_path: str) -> DistributionArchive:
    return DistributionArchive(artifact_path)
