"""Page-aware local reference corpus support.

The build dependency is optional. Reading and searching an existing corpus
uses only the Python standard library.

Reference knowledge is a separate subsystem: it never silently becomes
code-graph truth, and every result retains citation/evidence information.
"""

from .models import (
    AUTHORITY_RANK,
    CONTRACT_VERSION,
    BuildRequest,
    GraphifyRequest,
    ReferenceError,
    SourceDeclaration,
)
from .builder import build_reference_corpus
from .corpus import ReferenceCorpus
from .graphify_adapter import build_graphify_overlay

__all__ = [
    "AUTHORITY_RANK",
    "CONTRACT_VERSION",
    "BuildRequest",
    "GraphifyRequest",
    "ReferenceError",
    "SourceDeclaration",
    "ReferenceCorpus",
    "build_reference_corpus",
    "build_graphify_overlay",
]
