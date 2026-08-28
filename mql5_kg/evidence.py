"""Canonical evidence model for the MQL5 Knowledge Graph.

Every important relationship in the canonical graph preserves its origin,
confidence, and (where available) source location. This module is the single
source of truth for evidence vocabulary used by ``graph.py``, the resolver,
runtime enrichment, and the intelligence layer.

Evidence classes (what kind of source produced the evidence):

- ``code_graph``                 derived from static source analysis
- ``reference_document``         derived from the optional reference corpus
- ``external_compiler_evidence`` derived from operator-supplied compiler logs
- ``semantic_overlay_inference`` derived from an optional LLM/Graphify overlay

Relationship origins (how the relationship was produced):

- ``extracted``  directly observed in source (e.g. a call site token)
- ``resolved``   produced by repository-wide resolution (includes, calls)
- ``runtime``    produced by runtime/event semantics, not visible as source calls
- ``inferred``   produced by an optional semantic overlay; never canonical truth
"""

from __future__ import annotations

from typing import Any

# Evidence classes
CODE_GRAPH = "code_graph"
REFERENCE_DOCUMENT = "reference_document"
EXTERNAL_COMPILER_EVIDENCE = "external_compiler_evidence"
SEMANTIC_OVERLAY_INFERENCE = "semantic_overlay_inference"

EVIDENCE_CLASSES = frozenset(
    {
        CODE_GRAPH,
        REFERENCE_DOCUMENT,
        EXTERNAL_COMPILER_EVIDENCE,
        SEMANTIC_OVERLAY_INFERENCE,
    }
)

# Relationship origins
ORIGIN_EXTRACTED = "extracted"
ORIGIN_RESOLVED = "resolved"
ORIGIN_RUNTIME = "runtime"
ORIGIN_INFERRED = "inferred"

ORIGINS = frozenset(
    {ORIGIN_EXTRACTED, ORIGIN_RESOLVED, ORIGIN_RUNTIME, ORIGIN_INFERRED}
)

# Confidence policy
CONFIDENCE_EXACT = 1.0          # single unambiguous source-backed resolution
CONFIDENCE_RUNTIME = 0.9        # runtime rule with a specific trigger (OrderSend)
CONFIDENCE_RUNTIME_WEAK = 0.7   # runtime rule with an indirect trigger
CONFIDENCE_AMBIGUOUS = 0.65     # multiple candidate targets preserved as such
CONFIDENCE_UNRESOLVED = 0.5     # call to an external/unresolved target
CONFIDENCE_UNRESOLVED_INCLUDE = 0.35  # include could not be located
CONFIDENCE_INFERRED = 0.0       # semantic overlay sets its own confidence

# Resolution states for call targets
RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
UNRESOLVED = "unresolved"
INFERRED = "inferred"

RESOLUTION_STATES = frozenset({RESOLVED, AMBIGUOUS, UNRESOLVED, INFERRED})

# Evidence states reported by the kernel for a given location
EVIDENCE_AVAILABLE = "available"
EVIDENCE_STALE = "stale"
EVIDENCE_UNAVAILABLE = "unavailable"
EVIDENCE_UNKNOWN = "unknown"
EVIDENCE_NOT_APPLICABLE = "not_applicable"

EVIDENCE_STATES = frozenset(
    {
        EVIDENCE_AVAILABLE,
        EVIDENCE_STALE,
        EVIDENCE_UNAVAILABLE,
        EVIDENCE_UNKNOWN,
        EVIDENCE_NOT_APPLICABLE,
    }
)


def validate_origin(origin: str) -> None:
    """Raise ValueError for unknown relationship origins."""

    if origin not in ORIGINS:
        raise ValueError(f"origin {origin!r} is unsupported")


def validate_confidence(confidence: float) -> None:
    """Raise ValueError for out-of-range confidence values."""

    if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be between 0.0 and 1.0, got {confidence!r}")


def evidence_reference_dict(
    subject_id: str,
    origin: str,
    confidence: float,
    location: Any = None,
    state: str = "unknown",
    state_reason: str | None = None,
) -> dict[str, Any]:
    """Build a canonical evidence-reference dictionary for adapters."""

    validate_origin(origin)
    validate_confidence(confidence)
    value: dict[str, Any] = {
        "subject_id": subject_id,
        "origin": origin,
        "confidence": confidence,
        "state": state,
        "state_reason": state_reason,
    }
    if location is not None and getattr(location, "to_dict", None) is not None:
        value["location"] = location.to_dict()
    return value
