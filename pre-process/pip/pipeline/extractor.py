from __future__ import annotations

from adapters.local_artifact import LocalArtifactAdapter
from adapters.resolver_bridge import ResolverInspectorBridge
from pip_models import ExtractedMetadataRecord
from pipeline.legacy_fallback import LegacyFallbackExtractor


class PipDependencyExtractor:
    def __init__(self) -> None:
        self._artifact_adapter = LocalArtifactAdapter()
        self._bridge = ResolverInspectorBridge()
        self._legacy_fallback = LegacyFallbackExtractor()

    def extract_local_artifact(
        self,
        artifact_path: str,
        *,
        project_name: str | None = None,
        version: str | None = None,
        allow_legacy_fallback: bool = True,
    ) -> ExtractedMetadataRecord:
        job = self._artifact_adapter.prepare_job(
            artifact_path,
            project_name=project_name,
            version=version,
        )

        try:
            return self._bridge.extract(job)
        except Exception as exc:
            if not allow_legacy_fallback:
                raise
            return self._legacy_fallback.extract(job, primary_error=exc)
