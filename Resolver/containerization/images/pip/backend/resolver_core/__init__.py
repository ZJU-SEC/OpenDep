"""Resolver core package for pip dependency solving."""

from Resolver.containerization.images.pip.backend.resolver_core.candidates import Candidate
from Resolver.containerization.images.pip.backend.resolver_core.provider import PipProvider
from Resolver.containerization.images.pip.backend.resolver_core.requirements import (
    parse_requirement_strings,
)
from Resolver.containerization.images.pip.backend.resolver_core.service import ResolverCore

__all__ = ["Candidate", "PipProvider", "ResolverCore", "parse_requirement_strings"]
