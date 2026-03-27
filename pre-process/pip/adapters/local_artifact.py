from __future__ import annotations

from pathlib import Path

from pip_models import ExtractionJob
from resolving.containerization.images.pip.backend.inspectors.archive import (
    detect_artifact_kind,
    infer_name_version_from_filename,
)


def _detect_preprocess_artifact_kind(filename: str) -> str:
    if filename.endswith(".egg"):
        return "egg"
    return detect_artifact_kind(filename)


def _infer_preprocess_name_version(filename: str) -> tuple[str | None, str | None]:
    if filename.endswith(".egg"):
        stripped = filename[: -len(".egg")]
        if "-" not in stripped:
            return None, None
        name, version = stripped.rsplit("-", 1)
        return name or None, version or None
    return infer_name_version_from_filename(filename)


class LocalArtifactAdapter:
    SUPPORTED_KINDS = {"wheel", "sdist", "egg"}

    def prepare_job(
        self,
        artifact_path: str,
        *,
        project_name: str | None = None,
        version: str | None = None,
    ) -> ExtractionJob:
        path = Path(artifact_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"artifact path does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"artifact path is not a file: {path}")

        kind = _detect_preprocess_artifact_kind(path.name)
        if kind not in self.SUPPORTED_KINDS:
            raise ValueError(f"unsupported artifact type: {path.name}")

        inferred_name, inferred_version = _infer_preprocess_name_version(path.name)
        return ExtractionJob(
            artifact_path=str(path),
            artifact_kind=kind,
            filename=path.name,
            project_name=project_name or inferred_name,
            version=version or inferred_version,
        )
