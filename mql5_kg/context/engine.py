"""Deterministic structural context selection over one immutable graph index.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.

The context engine packs structural records under an explicit ``context_units``
budget. Relationships are packed atomically with both endpoint summaries;
ranking is deterministic; and omissions are always reported truthfully
(Invariant 8).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ..graph import GraphEdge, GraphNode, stable_id
from ..index import GraphIndex
from ..intelligence.models import (
    Completion,
    ContextItem,
    ContextPackage,
    EvidenceReference,
    IntelligenceBounds,
    NodeSummary,
    OmissionSummary,
)
from ..intelligence.traversal import EvidenceProbe, ORIGIN_PENALTY


@dataclass(frozen=True, slots=True)
class ContextPackageResult:
    """Internal package plus truthful completion metadata."""

    package: ContextPackage
    completion: Completion


@dataclass(frozen=True, slots=True)
class _CandidateGroup:
    key: tuple[int, int, int, int, str]
    category: str
    subject: Any


def _node_key(node: GraphNode) -> tuple[str, str, str]:
    return (node.qualified_name.casefold(), node.kind, node.id)


def _incident_edges(
    index: GraphIndex,
    node_id: str,
    direction: str,
) -> tuple[tuple[GraphEdge, str], ...]:
    candidates: dict[tuple[str, str], tuple[GraphEdge, str]] = {}
    if direction in {"outgoing", "both"}:
        for edge in index.outgoing.get(node_id, ()):
            candidates[(edge.id, edge.target)] = (edge, edge.target)
    if direction in {"incoming", "both"}:
        for edge in index.incoming.get(node_id, ()):
            candidates[(edge.id, edge.source)] = (edge, edge.source)
    return tuple(candidates[key] for key in sorted(candidates))


def _edge_evidence(
    edge: GraphEdge,
    probe: EvidenceProbe | None,
) -> EvidenceReference:
    if edge.location is None:
        state, reason = "unknown", "location_missing"
    elif probe is None:
        state, reason = "unknown", "probe_not_configured"
    else:
        state, reason = probe(edge)
    return EvidenceReference(
        subject_id=edge.id,
        origin=edge.origin,
        confidence=edge.confidence,
        location=edge.location,
        state=state,
        state_reason=reason,
    )


def _diagnostic_id(diagnostic) -> str:
    location_key = (
        f"{diagnostic.location.file}:{diagnostic.location.line}:"
        f"{diagnostic.location.column}"
        if diagnostic.location
        else ""
    )
    return stable_id(
        "diagnostic",
        diagnostic.severity,
        diagnostic.code,
        diagnostic.message,
        location_key,
    )


def _diagnostic_evidence(diagnostic_id: str, diagnostic) -> EvidenceReference:
    reason = (
        "location_missing"
        if diagnostic.location is None
        else "probe_not_configured"
    )
    return EvidenceReference(
        subject_id=diagnostic_id,
        origin="extracted",
        confidence=1.0,
        location=diagnostic.location,
        state="unknown",
        state_reason=reason,
    )


def assemble_context_package(
    index: GraphIndex,
    target_ids: Iterable[str],
    bounds: IntelligenceBounds,
    *,
    direction: str = "both",
    relationship_types: Iterable[str] = (),
    node_kinds: Iterable[str] = (),
    evidence_probe: EvidenceProbe | None = None,
) -> ContextPackageResult:
    """Rank and atomically pack structural records within ``context_units``."""

    allowed_relationships = frozenset(relationship_types)
    allowed_node_kinds = frozenset(node_kinds)
    targets = tuple(
        sorted(
            {
                node_id
                for node_id in target_ids
                if node_id in index.nodes
            },
            key=lambda node_id: _node_key(index.nodes[node_id]),
        )
    )
    if not targets:
        return ContextPackageResult(
            ContextPackage(bounds.context_units, 0),
            Completion(True, False, "no_match"),
        )

    distances = {node_id: 0 for node_id in targets}
    queue = deque(targets)
    encountered: dict[str, GraphEdge] = {}
    depth_limited = False
    expansion_limited = False
    while queue and not expansion_limited:
        current = queue.popleft()
        distance = distances[current]
        for edge, other in _incident_edges(index, current, direction):
            if edge.id in encountered:
                continue
            if allowed_relationships and edge.relationship not in allowed_relationships:
                continue
            if len(encountered) >= bounds.max_expansions:
                expansion_limited = True
                break
            encountered[edge.id] = edge
            if other not in index.nodes:
                continue
            if allowed_node_kinds and index.nodes[other].kind not in allowed_node_kinds:
                continue
            if distance >= bounds.max_depth:
                if other not in distances:
                    depth_limited = True
                continue
            if other not in distances:
                distances[other] = distance + 1
                queue.append(other)

    eligible_edges = tuple(
        edge
        for edge in encountered.values()
        if edge.source in distances and edge.target in distances
    )
    target_files = {
        index.nodes[node_id].location.file
        for node_id in targets
        if index.nodes[node_id].location is not None
    }

    groups: list[_CandidateGroup] = []
    for node_id in targets:
        groups.append(
            _CandidateGroup(
                (0, 0, 0, -10_000, node_id),
                "target",
                index.nodes[node_id],
            )
        )
    for edge in eligible_edges:
        distance = max(distances[edge.source], distances[edge.target])
        tier = 1 if distance <= 1 else 3
        groups.append(
            _CandidateGroup(
                (
                    tier,
                    distance,
                    ORIGIN_PENALTY.get(edge.origin, 99),
                    -int(round(edge.confidence * 10_000)),
                    edge.id,
                ),
                "relationship",
                edge,
            )
        )
    severity_order = {"error": 0, "warning": 1, "info": 2}
    for diagnostic in index.diagnostics:
        diagnostic_id = _diagnostic_id(diagnostic)
        local = (
            diagnostic.location is not None
            and diagnostic.location.file in target_files
        )
        groups.append(
            _CandidateGroup(
                (
                    2 if local else 4,
                    0 if local else bounds.max_depth + 1,
                    severity_order.get(diagnostic.severity, 99),
                    -10_000,
                    diagnostic_id,
                ),
                "diagnostic",
                (diagnostic_id, diagnostic),
            )
        )
    groups.sort(key=lambda group: group.key)

    selected_nodes: set[str] = set()
    selected_edges: set[str] = set()
    selected_diagnostics: set[str] = set()
    items: list[ContextItem] = []

    def append_item(
        category: str,
        distance: int,
        subject_id: str,
        summary: dict[str, Any],
        evidence: EvidenceReference | None = None,
    ) -> None:
        items.append(
            ContextItem(
                rank=len(items) + 1,
                category=category,
                distance=distance,
                subject_id=subject_id,
                summary=summary,
                evidence=evidence,
            )
        )

    for group in groups:
        remaining = bounds.context_units - len(items)
        if group.category == "target":
            node = group.subject
            if node.id in selected_nodes or remaining < 1:
                continue
            append_item(
                "target",
                0,
                node.id,
                NodeSummary.from_node(node).to_dict(),
            )
            selected_nodes.add(node.id)
            continue

        if group.category == "relationship":
            edge = group.subject
            missing_node_ids = tuple(
                sorted(
                    {
                        edge.source,
                        edge.target,
                    }
                    - selected_nodes,
                    key=lambda node_id: _node_key(index.nodes[node_id]),
                )
            )
            required = len(missing_node_ids) + 1
            if edge.id in selected_edges or remaining < required:
                continue
            for node_id in missing_node_ids:
                node = index.nodes[node_id]
                append_item(
                    "node",
                    distances[node_id],
                    node.id,
                    NodeSummary.from_node(node).to_dict(),
                )
                selected_nodes.add(node.id)
            append_item(
                "relationship",
                max(distances[edge.source], distances[edge.target]),
                edge.id,
                {
                    "id": edge.id,
                    "source": edge.source,
                    "target": edge.target,
                    "relationship": edge.relationship,
                },
                _edge_evidence(edge, evidence_probe),
            )
            selected_edges.add(edge.id)
            continue

        diagnostic_id, diagnostic = group.subject
        if diagnostic_id in selected_diagnostics or remaining < 1:
            continue
        append_item(
            "diagnostic",
            group.key[1],
            diagnostic_id,
            {
                "id": diagnostic_id,
                "severity": diagnostic.severity,
                "code": diagnostic.code,
                "message": diagnostic.message,
            },
            _diagnostic_evidence(diagnostic_id, diagnostic),
        )
        selected_diagnostics.add(diagnostic_id)

    eligible_nodes = set(targets)
    for edge in eligible_edges:
        eligible_nodes.update((edge.source, edge.target))
    eligible_diagnostic_ids = {
        _diagnostic_id(diagnostic) for diagnostic in index.diagnostics
    }
    omitted: dict[str, int | None] = {}
    omitted_nodes = len(eligible_nodes - selected_nodes)
    omitted_relationships = len({edge.id for edge in eligible_edges} - selected_edges)
    omitted_diagnostics = len(eligible_diagnostic_ids - selected_diagnostics)
    omitted_alternatives = len(set(targets) - selected_nodes) if len(targets) > 1 else 0
    if omitted_nodes:
        omitted["nodes"] = omitted_nodes
    if omitted_relationships:
        omitted["relationships"] = omitted_relationships
    if omitted_diagnostics:
        omitted["diagnostics"] = omitted_diagnostics
    if omitted_alternatives:
        omitted["ambiguity_alternatives"] = omitted_alternatives
    if expansion_limited or depth_limited:
        omitted["search_space"] = None

    package = ContextPackage(
        budget_limit=bounds.context_units,
        budget_used=len(items),
        items=tuple(items),
        omissions=tuple(
            OmissionSummary(category, count)
            for category, count in sorted(omitted.items())
        ),
    )
    if expansion_limited:
        completion = Completion(
            False,
            True,
            "max_expansions",
            {"context_items": None},
            explored_nodes=len(distances),
            explored_edges=len(encountered),
        )
    elif depth_limited:
        completion = Completion(
            False,
            True,
            "max_depth",
            {"context_items": None},
            explored_nodes=len(distances),
            explored_edges=len(encountered),
        )
    elif omitted:
        completion = Completion(
            True,
            True,
            "context_budget",
            omitted,
            explored_nodes=len(distances),
            explored_edges=len(encountered),
        )
    else:
        completion = Completion(
            True,
            False,
            "complete",
            explored_nodes=len(distances),
            explored_edges=len(encountered),
        )
    return ContextPackageResult(package, completion)


__all__ = ("ContextPackageResult", "assemble_context_package")
