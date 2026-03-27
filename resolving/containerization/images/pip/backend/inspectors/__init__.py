"""Artifact inspection utilities for the pip backend."""

from resolving.containerization.images.pip.backend.inspectors.base import DependencyInspector
from resolving.containerization.images.pip.backend.inspectors.sdist import (
    SdistDependencyInspector,
)
from resolving.containerization.images.pip.backend.inspectors.wheel import (
    WheelDependencyInspector,
)

__all__ = [
    "DependencyInspector",
    "SdistDependencyInspector",
    "WheelDependencyInspector",
]
