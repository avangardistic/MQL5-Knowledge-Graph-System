"""Deterministic bounded neighborhood and upstream-impact traversal.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ..graph import GraphEdge, GraphNode
from ..index import GraphIndex
from .models import (
    Completion,
    EvidenceReference,
    IntelligenceBounds,
    RelationshipResult,
)

EvidenceProbe = Callable[[GraphEdge], tuple[str, str | None]]

IMPACT_RELATIONSHIPS = frozenset(
    {"calls", "includes", "defines", "runtime_dispatches", "may_trigger_event"}
)
ORIGIN_PENALTY = {"extracted": 0, "resolved": 1, "runtime": 1, "inferred": 3}


@dataclass(frozen=True, slots=True)
class TraversalResult:
    """Internal traversal records plus contract completion metadata."""

    nodes: tuple[GraphNode, ...]
    relationships: tuple[RelationshipResult, ...]
    distances: tuple[tuple[str, int], ...]
    edge_paths: tuple[tuple[str, tuple[str, ...]], ...]
    completion: Completion

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(node.id for node in self.nodes)

    def distance_for(self, node_id: str) -> int | None:
        return dict(self.distances).get(node_id)

    def edge_path_for(self, node_id: str) -> tuple[str, ...]:
        return dict(self.edge_paths).get(node_id, ())


def _node_key(node: GraphNode, distance: int) -> tuple[int, str, str, str]:
    return (distance, node.kind, node.qualified_name.casefold(), node.id)


def _edge_evidence(
    edge: GraphEdge, probe: EvidenceProbe | None
) -> EvidenceReference:
    if probe is None:
        state = "unknown"
        reason = "location_missing" if edge.location is None else "probe_not_configured"
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


def _incident_edges(
    index: GraphIndex,
    node_id: str,
    direction: str,
) -> tuple[tuple[GraphEdge, str], ...]:
    candidates: list[tuple[GraphEdge, str]] = []
    if direction in {"outgoing", "both"}:
        candidates.extend(
            (edge, edge.target) for edge in index.outgoing.get(node_id, ())
        )
    if direction in {"incoming", "both"}:
        candidates.extend(
            (edge, edge.source) for edge in index.incoming.get(node_id, ())
        )
    return tuple(
        sorted(
            {(edge.id, other): (edge, other) for edge, other in candidates}.values(),
            key=lambda item: (item[0].id, item[1]),
        )
    )


def _traverse(
    index: GraphIndex,
    seed_ids: Iterable[str],
    bounds: IntelligenceBounds,
    *,
    direction: str,
    relationship_types: Iterable[str] = (),
    evidence_probe: EvidenceProbe | None = None,
) -> TraversalResult:
    allowed = frozenset(relationship_types)
    seeds = tuple(sorted({seed for seed in seed_ids if seed in index.nodes}))
    if not seeds:
        return TraversalResult(
            (),
            (),
            (),
            (),
            Completion(True, False, "no_match"),
        )

    distances = {seed: 0 for seed in seeds}
    paths = {seed: () for seed in seeds}
    queue = deque(seeds)
    encountered_edges: set[str] = set()
    depth_limited = False
    while queue:
        current = queue.popleft()
        distance = distances[current]
        for edge, other in _incident_edges(index, current, direction):
            if allowed and edge.relationship not in allowed:
                continue
            encountered_edges.add(edge.id)
            if other not in index.nodes:
                continue
            if distance >= bounds.max_depth:
                if other not in distances:
                    depth_limited = True
                continue
            candidate_distance = distance + 1
            if other not in distances:
                distances[other] = candidate_distance
                paths[other] = paths[current] + (edge.id,)
                queue.append(other)

    ordered_nodes = tuple(
        sorted(
            (index.nodes[node_id] for node_id in distances),
            key=lambda node: _node_key(node, distances[node.id]),
        )
    )
    output_truncated = len(ordered_nodes) > bounds.max_items
    selected_nodes = ordered_nodes[: bounds.max_items]
    selected_ids = {node.id for node in selected_nodes}

    relationship_edges = [
        index.edges[edge_id]
        for edge_id in encountered_edges
        if index.edges[edge_id].source in selected_ids
        and index.edges[edge_id].target in selected_ids
    ]
    relationship_edges.sort(
        key=lambda edge: (
            max(distances[edge.source], distances[edge.target]),
            ORIGIN_PENALTY.get(edge.origin, 99),
            edge.relationship,
            edge.source,
            edge.target,
            edge.id,
        )
    )
    relationships = tuple(
        RelationshipResult(
            id=edge.id,
            source=edge.source,
            target=edge.target,
            relationship=edge.relationship,
            evidence=_edge_evidence(edge, evidence_probe),
        )
        for edge in relationship_edges
    )

    if depth_limited:
        completion = Completion(
            False,
            True,
            "max_depth",
            {"nodes": None},
            explored_nodes=len(distances),
            explored_edges=len(encountered_edges),
        )
    elif output_truncated:
        completion = Completion(
            True,
            True,
            "max_items",
            {"nodes": len(ordered_nodes) - len(selected_nodes)},
            explored_nodes=len(distances),
            explored_edges=len(encountered_edges),
        )
    else:
        completion = Completion(
            True,
            False,
            "complete",
            explored_nodes=len(distances),
            explored_edges=len(encountered_edges),
        )
    return TraversalResult(
        selected_nodes,
        relationships,
        tuple(sorted(distances.items())),
        tuple(sorted((node_id, paths[node_id]) for node_id in distances)),
        completion,
    )


def traverse_context(
    index: GraphIndex,
    seed_ids: Iterable[str],
    bounds: IntelligenceBounds,
    *,
    direction: str = "both",
    relationship_types: Iterable[str] = (),
    evidence_probe: EvidenceProbe | None = None,
) -> TraversalResult:
    """Return a bounded deterministic neighborhood around resolved seeds."""

    return _traverse(
        index,
        seed_ids,
        bounds,
        direction=direction,
        relationship_types=relationship_types,
        evidence_probe=evidence_probe,
    )


def traverse_impact(
    index: GraphIndex,
    seed_ids: Iterable[str],
    bounds: IntelligenceBounds,
    *,
    relationship_types: Iterable[str] = (),
    evidence_probe: EvidenceProbe | None = None,
) -> TraversalResult:
    """Return bounded upstream impact using the explicit legacy policy."""

    policy = tuple(relationship_types) or tuple(sorted(IMPACT_RELATIONSHIPS))
    return _traverse(
        index,
        seed_ids,
        bounds,
        direction="incoming",
        relationship_types=policy,
        evidence_probe=evidence_probe,
    )
