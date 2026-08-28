"""Deterministic evidence-first bounded directed path search.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count
from threading import RLock

from ..graph import GraphEdge
from ..index import GraphIndex
from .models import (
    Completion,
    DirectedPath,
    EvidenceReference,
    IntelligenceBounds,
    PathHop,
)

EvidenceProbe = Callable[[GraphEdge], tuple[str, str | None]]

ORIGIN_PENALTY = {"extracted": 0, "resolved": 1, "runtime": 1, "inferred": 3}
DEGRADED_EVIDENCE_STATES = frozenset({"stale", "unavailable"})
TARGET_DISTANCE_CACHE_CAPACITY = 64


@dataclass(frozen=True, slots=True)
class PathSearchResult:
    """Pure path-search output prior to kernel envelope projection."""

    paths: tuple[DirectedPath, ...]
    completion: Completion

    def __post_init__(self) -> None:
        object.__setattr__(self, "paths", tuple(self.paths))


@dataclass(frozen=True, slots=True)
class _SearchState:
    node_ids: tuple[str, ...]
    hops: tuple[PathHop, ...]
    edge_ids: tuple[str, ...]
    weak_hops: int
    degraded_evidence: int
    origin_penalty: int
    minimum_confidence_bps: int

    @property
    def current_id(self) -> str:
        return self.node_ids[-1]

    @property
    def ranking_key(
        self,
    ) -> tuple[int, int, int, int, int, tuple[str, ...]]:
        return (
            self.weak_hops,
            self.degraded_evidence,
            len(self.hops),
            self.origin_penalty,
            -self.minimum_confidence_bps,
            self.edge_ids,
        )


def _confidence_bps(confidence: float) -> int:
    return int(round(confidence * 10_000))


def _is_ambiguous(edge: GraphEdge) -> bool:
    status = str(edge.attributes.get("resolution_status", "")).casefold()
    return bool(edge.attributes.get("ambiguous")) or status == "ambiguous"


def _evidence_for(
    edge: GraphEdge,
    probe: EvidenceProbe | None,
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


def _transitions(
    index: GraphIndex,
    node_id: str,
    direction: str,
) -> tuple[tuple[GraphEdge, str, str], ...]:
    candidates: dict[tuple[str, str, str], tuple[GraphEdge, str, str]] = {}
    if direction in {"outgoing", "both"}:
        for edge in index.outgoing.get(node_id, ()):
            item = (edge, edge.target, "forward")
            candidates[(edge.id, "forward", edge.target)] = item
    if direction in {"incoming", "both"}:
        for edge in index.incoming.get(node_id, ()):
            item = (edge, edge.source, "reverse")
            candidates[(edge.id, "reverse", edge.source)] = item
    return tuple(
        candidates[key]
        for key in sorted(candidates, key=lambda item: (item[0], item[1], item[2]))
    )


def _minimum_hops_to_targets(
    index: GraphIndex,
    target_ids: Iterable[str],
    direction: str,
    allowed_relationships: frozenset[str],
) -> dict[str, int]:
    """Return an optimistic target-distance lower bound for safe branch pruning."""

    predecessors: dict[str, set[str]] = {}
    for edge in index.edges.values():
        if allowed_relationships and edge.relationship not in allowed_relationships:
            continue
        if direction in {"outgoing", "both"}:
            predecessors.setdefault(edge.target, set()).add(edge.source)
        if direction in {"incoming", "both"}:
            predecessors.setdefault(edge.source, set()).add(edge.target)

    distances = {target_id: 0 for target_id in target_ids}
    pending = deque(sorted(distances))
    while pending:
        node_id = pending.popleft()
        distance = distances[node_id] + 1
        for predecessor_id in sorted(predecessors.get(node_id, ())):
            if predecessor_id in distances:
                continue
            distances[predecessor_id] = distance
            pending.append(predecessor_id)
    return distances


class TargetDistanceCache:
    """Thread-safe bounded target distances owned by one immutable graph index."""

    __slots__ = ("_entries", "_index", "_lock", "_max_entries")

    def __init__(
        self,
        index: GraphIndex,
        *,
        max_entries: int = TARGET_DISTANCE_CACHE_CAPACITY,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._index = index
        self._max_entries = max_entries
        self._entries: OrderedDict[
            tuple[tuple[str, ...], str, tuple[str, ...]],
            dict[str, int],
        ] = OrderedDict()
        self._lock = RLock()

    def get(
        self,
        index: GraphIndex,
        target_ids: Iterable[str],
        direction: str,
        allowed_relationships: frozenset[str],
    ) -> Mapping[str, int]:
        if index is not self._index:
            raise ValueError("target-distance cache belongs to another graph index")
        key = (
            tuple(sorted(set(target_ids))),
            direction,
            tuple(sorted(allowed_relationships)),
        )
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                return cached

            distances = _minimum_hops_to_targets(
                index,
                key[0],
                direction,
                frozenset(key[2]),
            )
            self._entries[key] = distances
            if len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
            return distances


def _completion(
    *,
    path_count: int,
    selected_count: int,
    limiting_reason: str | None,
    explored_nodes: int,
    explored_edges: int,
) -> Completion:
    if limiting_reason is not None:
        return Completion(
            False,
            True,
            limiting_reason,
            {"paths": None},
            explored_nodes=explored_nodes,
            explored_edges=explored_edges,
        )
    if path_count == 0:
        return Completion(
            True,
            False,
            "not_connected",
            explored_nodes=explored_nodes,
            explored_edges=explored_edges,
        )
    omitted = path_count - selected_count
    if omitted:
        return Completion(
            True,
            True,
            "max_paths",
            {"paths": omitted},
            explored_nodes=explored_nodes,
            explored_edges=explored_edges,
        )
    return Completion(
        True,
        False,
        "complete",
        explored_nodes=explored_nodes,
        explored_edges=explored_edges,
    )


def find_directed_paths(
    index: GraphIndex,
    source_id: str,
    target_id: str,
    bounds: IntelligenceBounds,
    *,
    direction: str = "outgoing",
    relationship_types: Iterable[str] = (),
    evidence_probe: EvidenceProbe | None = None,
) -> PathSearchResult:
    """Return deterministically ranked simple paths within explicit search bounds."""

    return find_directed_paths_between(
        index,
        (source_id,),
        (target_id,),
        bounds,
        direction=direction,
        relationship_types=relationship_types,
        evidence_probe=evidence_probe,
    )


def find_directed_paths_between(
    index: GraphIndex,
    source_ids: Iterable[str],
    target_ids: Iterable[str],
    bounds: IntelligenceBounds,
    *,
    direction: str = "outgoing",
    relationship_types: Iterable[str] = (),
    evidence_probe: EvidenceProbe | None = None,
    _distance_cache: TargetDistanceCache | None = None,
) -> PathSearchResult:
    """Search all resolved source/target alternatives under one shared budget."""

    if direction not in {"incoming", "outgoing", "both"}:
        raise ValueError("direction must be incoming, outgoing, or both")
    sources = tuple(sorted({item for item in source_ids if item in index.nodes}))
    targets = frozenset(item for item in target_ids if item in index.nodes)
    if not sources or not targets:
        return PathSearchResult(
            (),
            Completion(True, False, "no_match"),
        )

    allowed_relationships = frozenset(relationship_types)
    evidence_cache: dict[str, EvidenceReference] = {}
    transition_cache: dict[str, tuple[tuple[GraphEdge, str, str], ...]] = {}
    minimum_hops = (
        _distance_cache.get(
            index,
            targets,
            direction,
            allowed_relationships,
        )
        if _distance_cache is not None
        else _minimum_hops_to_targets(
            index,
            targets,
            direction,
            allowed_relationships,
        )
    )

    def evidence_for(edge: GraphEdge) -> EvidenceReference:
        evidence = evidence_cache.get(edge.id)
        if evidence is None:
            evidence = _evidence_for(edge, evidence_probe)
            evidence_cache[edge.id] = evidence
        return evidence

    def transitions_for(node_id: str) -> tuple[tuple[GraphEdge, str, str], ...]:
        transitions = transition_cache.get(node_id)
        if transitions is None:
            transitions = tuple(
                transition
                for transition in _transitions(index, node_id, direction)
                if not allowed_relationships
                or transition[0].relationship in allowed_relationships
            )
            transition_cache[node_id] = transitions
        return transitions

    serial = count()
    frontier: list[
        tuple[
            tuple[int, int, int, int, int, tuple[str, ...]],
            int,
            _SearchState,
        ]
    ] = []
    for source_id in sources:
        initial = _SearchState(
            node_ids=(source_id,),
            hops=(),
            edge_ids=(),
            weak_hops=0,
            degraded_evidence=0,
            origin_penalty=0,
            minimum_confidence_bps=10_000,
        )
        heappush(frontier, (initial.ranking_key, next(serial), initial))

    candidates: list[_SearchState] = []
    explored_node_ids: set[str] = set()
    explored_edges = 0
    limiting_reason: str | None = None
    stop_search = False

    while frontier and not stop_search:
        _, _, state = heappop(frontier)
        explored_node_ids.add(state.current_id)
        if state.current_id in targets:
            candidates.append(state)
            if len(candidates) > bounds.max_paths and frontier:
                if limiting_reason is None:
                    limiting_reason = "max_paths"
                stop_search = True
            continue

        transitions = transitions_for(state.current_id)
        if len(state.hops) >= bounds.max_depth:
            if any(
                other_id not in state.node_ids and other_id in minimum_hops
                for _, other_id, _ in transitions
            ):
                if limiting_reason is None:
                    limiting_reason = "max_depth"
            continue

        for edge, other_id, hop_direction in transitions:
            if explored_edges >= bounds.max_expansions:
                if limiting_reason is None:
                    limiting_reason = "max_expansions"
                stop_search = True
                break
            explored_edges += 1
            if other_id in state.node_ids:
                continue
            remaining_depth = bounds.max_depth - len(state.hops) - 1
            target_distance = minimum_hops.get(other_id)
            if target_distance is None:
                continue
            if target_distance > remaining_depth:
                if limiting_reason is None:
                    limiting_reason = "max_depth"
                continue

            evidence = evidence_for(edge)
            hop = PathHop(
                source_id=state.current_id,
                target_id=other_id,
                edge_id=edge.id,
                relationship=edge.relationship,
                direction=hop_direction,
                evidence=evidence,
            )
            next_state = _SearchState(
                node_ids=state.node_ids + (other_id,),
                hops=state.hops + (hop,),
                edge_ids=state.edge_ids + (edge.id,),
                weak_hops=state.weak_hops
                + int(edge.origin == "inferred" or _is_ambiguous(edge)),
                degraded_evidence=state.degraded_evidence
                + int(evidence.state in DEGRADED_EVIDENCE_STATES),
                origin_penalty=state.origin_penalty
                + ORIGIN_PENALTY.get(edge.origin, 99),
                minimum_confidence_bps=min(
                    state.minimum_confidence_bps,
                    _confidence_bps(edge.confidence),
                ),
            )
            heappush(
                frontier,
                (next_state.ranking_key, next(serial), next_state),
            )

    ordered = tuple(sorted(candidates, key=lambda item: item.ranking_key))
    selected = ordered[: bounds.max_paths]
    paths = tuple(
        DirectedPath(
            rank=rank,
            node_ids=state.node_ids,
            hops=state.hops,
        )
        for rank, state in enumerate(selected, start=1)
    )
    completion = _completion(
        path_count=len(ordered),
        selected_count=len(selected),
        limiting_reason=limiting_reason,
        explored_nodes=len(explored_node_ids),
        explored_edges=explored_edges,
    )
    return PathSearchResult(paths, completion)
