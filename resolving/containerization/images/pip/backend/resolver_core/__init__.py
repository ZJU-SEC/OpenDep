"""resolving core package for pip dependency solving."""

from resolving.containerization.images.pip.backend.resolver_core.candidates import Candidate
from resolving.containerization.images.pip.backend.resolver_core.provider import PipProvider
from resolving.containerization.images.pip.backend.resolver_core.requirements import (
    parse_requirement_strings,
)
from resolving.containerization.images.pip.backend.resolver_core.service import ResolverCore

__all__ = ["Candidate", "PipProvider", "ResolverCore", "parse_requirement_strings"]
