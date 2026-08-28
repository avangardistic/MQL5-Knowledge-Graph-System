"""Intelligence Kernel: versioned semantic queries over one immutable graph."""

from .errors import IntelligenceError
from .kernel import IntelligenceKernel
from .matching import resolve_target
from .models import (
    CONTRACT_VERSION,
    Completion,
    ContextItem,
    ContextPackage,
    DirectedPath,
    EvidenceReference,
    GraphIdentity,
    IntelligenceBounds,
    IntelligenceRequest,
    IntelligenceResult,
    NodeSummary,
    PathHop,
    RelationshipResult,
    SymbolSelector,
    TargetResolution,
    canonical_json,
)

__all__ = [
    "CONTRACT_VERSION",
    "Completion",
    "ContextItem",
    "ContextPackage",
    "DirectedPath",
    "EvidenceReference",
    "GraphIdentity",
    "IntelligenceBounds",
    "IntelligenceError",
    "IntelligenceKernel",
    "IntelligenceRequest",
    "IntelligenceResult",
    "NodeSummary",
    "PathHop",
    "RelationshipResult",
    "SymbolSelector",
    "TargetResolution",
    "canonical_json",
    "resolve_target",
]
