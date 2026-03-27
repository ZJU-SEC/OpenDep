from __future__ import annotations

from pip_models import ExtractionJob, ExtractedMetadataRecord
from resolving.containerization.images.pip.backend.inspectors.sdist import (
    SdistDependencyInspector,
)
from resolving.containerization.images.pip.backend.inspectors.wheel import (
    WheelDependencyInspector,
)


class ResolverInspectorBridge:
    def __init__(self) -> None:
        self._wheel = WheelDependencyInspector()
        self._sdist = SdistDependencyInspector()

    def extract(self, job: ExtractionJob) -> ExtractedMetadataRecord:
        if job.artifact_kind == "wheel":
            record = self._wheel.inspect_distribution(
                job.artifact_path,
                project_name=job.project_name,
                version=job.version,
            )
            return ExtractedMetadataRecord.from_package_metadata(
                record,
                artifact_path=job.artifact_path,
                artifact_kind=job.artifact_kind,
                filename=job.filename,
                extraction_backend="resolver-inspector",
            )

        if job.artifact_kind == "sdist":
            record = self._sdist.inspect_distribution(
                job.artifact_path,
                project_name=job.project_name,
                version=job.version,
            )
            return ExtractedMetadataRecord.from_package_metadata(
                record,
                artifact_path=job.artifact_path,
                artifact_kind=job.artifact_kind,
                filename=job.filename,
                extraction_backend="resolver-inspector",
            )

        raise ValueError(f"resolver inspector bridge does not support `{job.artifact_kind}` artifacts")
