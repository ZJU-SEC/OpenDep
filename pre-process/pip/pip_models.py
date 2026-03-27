from __future__ import annotations

import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[2]
COMMON_MODELS_ROOT = PROJECT_ROOT / "pre-process" / "common" / "models"

for path in (PROJECT_ROOT, COMMON_MODELS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from pip_records import (
    AcquiredArtifact,
    BatchBuildItemResult,
    BatchBuildSummary,
    BuildRequest,
    BuildJobSpec,
    ExtractedMetadataRecord,
    ExtractionFailureRecord,
    ExtractionJob,
    ValidatedExtractionResult,
    ValidationIssue,
    VersionPlanItem,
    artifact_filename,
    utc_now_iso,
)


__all__ = [
    "AcquiredArtifact",
    "BatchBuildItemResult",
    "BatchBuildSummary",
    "BuildRequest",
    "BuildJobSpec",
    "ExtractedMetadataRecord",
    "ExtractionFailureRecord",
    "ExtractionJob",
    "ValidatedExtractionResult",
    "ValidationIssue",
    "VersionPlanItem",
    "artifact_filename",
    "utc_now_iso",
]
