"""Immutable, deterministic contract models for Intelligence Kernel v1.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from types import MappingProxyType
from typing import Any, Mapping

from ..graph import GraphNode, SourceLocation

CONTRACT_VERSION = "1.0.0"
SUPPORTED_CONTRACT_MAJOR = 1
SUPPORTED_OPERATIONS = frozenset(
    {"query", "context", "impact", "diagnostics", "path", "context_package"}
)
SUPPORTED_DIRECTIONS = frozenset({"incoming", "outgoing", "both"})
SUPPORTED_ORIGINS = frozenset({"extracted", "resolved", "runtime", "inferred"})
SUPPORTED_EVIDENCE_STATES = frozenset(
    {"available", "stale", "unavailable", "unknown", "not_applicable"}
)
COMPLETION_REASONS = frozenset(
    {
        "complete",
        "no_match",
        "not_connected",
        "max_depth",
        "max_items",
        "max_paths",
        "max_expansions",
        "context_budget",
    }
)


def _version_major(value: str) -> int:
    try:
        major, minor, patch = value.split(".")
        if not all(part.isdigit() for part in (major, minor, patch)):
            raise ValueError
        return int(major)
    except (AttributeError, ValueError) as error:
        raise ValueError("contract_version must be a semantic version") from error


def _as_dict(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _as_dict(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_as_dict(item) for item in value]
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize a contract value deterministically as canonical readable JSON."""

    return json.dumps(
        _as_dict(value), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"


@dataclass(frozen=True, slots=True)
class IntelligenceBounds:
    max_depth: int = 1
    max_items: int = 30
    max_paths: int = 3
    max_expansions: int = 10_000
    context_units: int = 100

    def __post_init__(self) -> None:
        limits = {
            "max_depth": (self.max_depth, 0, 5),
            "max_items": (self.max_items, 1, 2000),
            "max_paths": (self.max_paths, 1, 20),
            "max_expansions": (self.max_expansions, 1, 100_000),
            "context_units": (self.context_units, 1, 10_000),
        }
        for field_name, (value, minimum, maximum) in limits.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field_name} must be an integer")
            if not minimum <= value <= maximum:
                raise ValueError(
                    f"{field_name} must be between {minimum} and {maximum}"
                )

    def to_dict(self) -> dict[str, int]:
        return {
            "max_depth": self.max_depth,
            "max_items": self.max_items,
            "max_paths": self.max_paths,
            "max_expansions": self.max_expansions,
            "context_units": self.context_units,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "IntelligenceBounds":
        return cls(**dict(value))


@dataclass(frozen=True, slots=True)
class SymbolSelector:
    value: str
    kind: str | None = None

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not normalized:
            raise ValueError("selector.value must be non-empty")
        object.__setattr__(self, "value", normalized)
        if self.kind is not None and not self.kind.strip():
            raise ValueError("selector.kind must be non-empty when provided")

    def to_dict(self) -> dict[str, str | None]:
        return {"value": self.value, "kind": self.kind}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SymbolSelector":
        return cls(value=str(value.get("value", "")), kind=value.get("kind"))


@dataclass(frozen=True, slots=True)
class IntelligenceRequest:
    operation: str
    targets: tuple[SymbolSelector, ...] = ()
    direction: str = "both"
    relationship_types: tuple[str, ...] = ()
    node_kinds: tuple[str, ...] = ()
    bounds: IntelligenceBounds = field(default_factory=IntelligenceBounds)
    expected_source_fingerprint: str | None = None
    client_request_id: str | None = None
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if _version_major(self.contract_version) != SUPPORTED_CONTRACT_MAJOR:
            raise ValueError(
                f"contract_version major {self.contract_version!r} is unsupported"
            )
        if self.operation not in SUPPORTED_OPERATIONS:
            raise ValueError(f"operation {self.operation!r} is unsupported")
        if self.direction not in SUPPORTED_DIRECTIONS:
            raise ValueError(f"direction {self.direction!r} is unsupported")
        if len(self.targets) > 2:
            raise ValueError("targets may contain at most two selectors")
        object.__setattr__(self, "targets", tuple(self.targets))
        object.__setattr__(
            self, "relationship_types", tuple(sorted(set(self.relationship_types)))
        )
        object.__setattr__(self, "node_kinds", tuple(sorted(set(self.node_kinds))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "operation": self.operation,
            "targets": [target.to_dict() for target in self.targets],
            "direction": self.direction,
            "relationship_types": list(self.relationship_types),
            "node_kinds": list(self.node_kinds),
            "bounds": self.bounds.to_dict(),
            "expected_source_fingerprint": self.expected_source_fingerprint,
            "client_request_id": self.client_request_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "IntelligenceRequest":
        known = {
            "contract_version",
            "operation",
            "targets",
            "direction",
            "relationship_types",
            "node_kinds",
            "bounds",
            "expected_source_fingerprint",
            "client_request_id",
        }
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"unknown request fields: {sorted(unknown)!r}")
        return cls(
            contract_version=str(value.get("contract_version", CONTRACT_VERSION)),
            operation=str(value.get("operation", "")),
            targets=tuple(
                SymbolSelector.from_dict(item) for item in value.get("targets", ())
            ),
            direction=str(value.get("direction", "both")),
            relationship_types=tuple(value.get("relationship_types", ())),
            node_kinds=tuple(value.get("node_kinds", ())),
            bounds=IntelligenceBounds.from_dict(value.get("bounds", {})),
            expected_source_fingerprint=value.get("expected_source_fingerprint"),
            client_request_id=value.get("client_request_id"),
        )


@dataclass(frozen=True, slots=True)
class GraphIdentity:
    graph_schema_version: str
    source_fingerprint: str | None
    snapshot_revision: int | None = None

    def __post_init__(self) -> None:
        if self.snapshot_revision is not None and self.snapshot_revision < 0:
            raise ValueError("snapshot_revision must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_schema_version": self.graph_schema_version,
            "source_fingerprint": self.source_fingerprint,
            "snapshot_revision": self.snapshot_revision,
        }


@dataclass(frozen=True, slots=True)
class NodeSummary:
    id: str
    kind: str
    name: str
    qualified_name: str
    location: SourceLocation | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "attributes", MappingProxyType(dict(self.attributes))
        )

    @classmethod
    def from_node(cls, node: GraphNode) -> "NodeSummary":
        return cls(
            id=node.id,
            kind=node.kind,
            name=node.name,
            qualified_name=node.qualified_name,
            location=node.location,
            attributes=node.attributes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "location": self.location.to_dict() if self.location else None,
            "attributes": _as_dict(self.attributes),
        }


@dataclass(frozen=True, slots=True)
class CandidateMatch:
    node_id: str
    match_rank: int

    def __post_init__(self) -> None:
        if not 0 <= self.match_rank <= 3:
            raise ValueError("match_rank must be between 0 and 3")

    def to_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "match_rank": self.match_rank}


@dataclass(frozen=True, slots=True)
class TargetResolution:
    selector: SymbolSelector
    status: str
    candidates: tuple[CandidateMatch, ...] = ()
    omitted_candidates: int | None = None

    def __post_init__(self) -> None:
        if self.status not in {"matched", "ambiguous", "no_match"}:
            raise ValueError(f"resolution status {self.status!r} is unsupported")
        object.__setattr__(self, "candidates", tuple(self.candidates))
        if self.omitted_candidates is not None and self.omitted_candidates < 0:
            raise ValueError("omitted_candidates must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "selector": self.selector.to_dict(),
            "status": self.status,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "omitted_candidates": self.omitted_candidates,
        }


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    subject_id: str
    origin: str
    confidence: float
    location: SourceLocation | None = None
    state: str = "unknown"
    state_reason: str | None = None

    def __post_init__(self) -> None:
        if self.origin not in SUPPORTED_ORIGINS:
            raise ValueError(f"origin {self.origin!r} is unsupported")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if self.state not in SUPPORTED_EVIDENCE_STATES:
            raise ValueError(f"evidence state {self.state!r} is unsupported")

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "origin": self.origin,
            "confidence": self.confidence,
            "location": self.location.to_dict() if self.location else None,
            "state": self.state,
            "state_reason": self.state_reason,
        }


@dataclass(frozen=True, slots=True)
class RelationshipResult:
    id: str
    source: str
    target: str
    relationship: str
    evidence: EvidenceReference

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relationship": self.relationship,
            "evidence": self.evidence.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PathHop:
    source_id: str
    target_id: str
    edge_id: str
    relationship: str
    direction: str
    evidence: EvidenceReference

    def __post_init__(self) -> None:
        if self.direction not in {"forward", "reverse"}:
            raise ValueError("path direction must be forward or reverse")

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(
            {
                "source_id": self.source_id,
                "target_id": self.target_id,
                "edge_id": self.edge_id,
                "relationship": self.relationship,
                "direction": self.direction,
                "evidence": self.evidence,
            }
        )


@dataclass(frozen=True, slots=True)
class DirectedPath:
    rank: int
    node_ids: tuple[str, ...]
    hops: tuple[PathHop, ...]
    ranking_policy: str = "evidence_first_v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_ids", tuple(self.node_ids))
        object.__setattr__(self, "hops", tuple(self.hops))
        if self.rank < 1:
            raise ValueError("path rank must be positive")
        if len(self.node_ids) != len(self.hops) + 1:
            raise ValueError("path node_ids must contain one more item than hops")

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(
            {
                "rank": self.rank,
                "node_ids": self.node_ids,
                "hops": self.hops,
                "ranking_policy": self.ranking_policy,
            }
        )


@dataclass(frozen=True, slots=True)
class OmissionSummary:
    category: str
    count: int | None

    def __post_init__(self) -> None:
        if self.count is not None and self.count < 0:
            raise ValueError("omission count must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {"category": self.category, "count": self.count}


@dataclass(frozen=True, slots=True)
class ContextItem:
    rank: int
    category: str
    distance: int
    subject_id: str
    summary: Mapping[str, Any]
    evidence: EvidenceReference | None = None
    cost_units: int = 1

    def __post_init__(self) -> None:
        if self.rank < 1 or self.distance < 0 or self.cost_units != 1:
            raise ValueError("invalid context item rank, distance, or cost_units")
        object.__setattr__(self, "summary", dict(self.summary))

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(
            {
                "rank": self.rank,
                "category": self.category,
                "distance": self.distance,
                "cost_units": self.cost_units,
                "subject_id": self.subject_id,
                "summary": self.summary,
                "evidence": self.evidence,
            }
        )


@dataclass(frozen=True, slots=True)
class ContextPackage:
    budget_limit: int
    budget_used: int
    items: tuple[ContextItem, ...] = ()
    omissions: tuple[OmissionSummary, ...] = ()
    budget_kind: str = "structural_record_v1"

    def __post_init__(self) -> None:
        if not 1 <= self.budget_limit <= 10_000:
            raise ValueError("budget_limit must be between 1 and 10000")
        if not 0 <= self.budget_used <= self.budget_limit:
            raise ValueError("budget_used must be within budget_limit")
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "omissions", tuple(self.omissions))

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(
            {
                "budget_kind": self.budget_kind,
                "budget_limit": self.budget_limit,
                "budget_used": self.budget_used,
                "items": self.items,
                "omissions": self.omissions,
            }
        )


@dataclass(frozen=True, slots=True)
class Completion:
    search_complete: bool
    truncated: bool
    reason: str
    omitted_counts: Mapping[str, int | None] = field(default_factory=dict)
    explored_nodes: int = 0
    explored_edges: int = 0

    def __post_init__(self) -> None:
        if self.reason not in COMPLETION_REASONS:
            raise ValueError(f"completion reason {self.reason!r} is unsupported")
        if self.explored_nodes < 0 or self.explored_edges < 0:
            raise ValueError("explored counts must be non-negative")
        object.__setattr__(
            self, "omitted_counts", dict(sorted(self.omitted_counts.items()))
        )

    @classmethod
    def complete(cls) -> "Completion":
        return cls(True, False, "complete")

    def to_dict(self) -> dict[str, Any]:
        return {
            "search_complete": self.search_complete,
            "truncated": self.truncated,
            "reason": self.reason,
            "omitted_counts": dict(self.omitted_counts),
            "explored_nodes": self.explored_nodes,
            "explored_edges": self.explored_edges,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    id: str
    severity: str
    code: str
    message: str
    evidence: EvidenceReference

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(
            {
                "id": self.id,
                "severity": self.severity,
                "code": self.code,
                "message": self.message,
                "evidence": self.evidence,
            }
        )


@dataclass(frozen=True, slots=True)
class IntelligenceResult:
    operation: str
    graph_identity: GraphIdentity
    request: IntelligenceRequest
    completion: Completion
    resolution: tuple[TargetResolution, ...] = ()
    nodes: tuple[Any, ...] = ()
    relationships: tuple[RelationshipResult, ...] = ()
    paths: tuple[DirectedPath, ...] = ()
    context_package: ContextPackage | None = None
    diagnostics: tuple[DiagnosticResult, ...] = ()
    limits_applied: IntelligenceBounds | None = None
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.operation != self.request.operation:
            raise ValueError("result operation must match request operation")
        if _version_major(self.contract_version) != SUPPORTED_CONTRACT_MAJOR:
            raise ValueError("result contract_version is unsupported")
        for name in ("resolution", "nodes", "relationships", "paths", "diagnostics"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if self.limits_applied is None:
            object.__setattr__(self, "limits_applied", self.request.bounds)

    def to_dict(self) -> dict[str, Any]:
        return _as_dict(
            {
                "contract_version": self.contract_version,
                "operation": self.operation,
                "graph_identity": self.graph_identity,
                "request": self.request,
                "resolution": self.resolution,
                "nodes": self.nodes,
                "relationships": self.relationships,
                "paths": self.paths,
                "context_package": self.context_package,
                "diagnostics": self.diagnostics,
                "limits_applied": self.limits_applied,
                "completion": self.completion,
            }
        )

    def to_json(self) -> str:
        return canonical_json(self)
