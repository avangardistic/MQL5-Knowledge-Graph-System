"""Deterministic symbol matching that preserves equal-ranked ambiguity.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

from ..index import GraphIndex
from .models import CandidateMatch, SymbolSelector, TargetResolution


def resolve_target(
    index: GraphIndex, selector: SymbolSelector
) -> TargetResolution:
    """Resolve a selector without converting ambiguous matches into certainty."""

    needle = selector.value.casefold()
    eligible = tuple(
        node
        for node in index.nodes.values()
        if selector.kind is None or node.kind == selector.kind
    )
    ranked: list[tuple[int, object]] = []
    for node in eligible:
        if node.id == selector.value:
            rank = 0
        elif node.qualified_name.casefold() == needle:
            rank = 1
        elif node.name.casefold() == needle:
            rank = 2
        elif needle in node.name.casefold() or needle in node.qualified_name.casefold():
            rank = 3
        else:
            continue
        ranked.append((rank, node))

    if not ranked:
        return TargetResolution(selector, "no_match")
    best_rank = min(rank for rank, _ in ranked)
    matches = sorted(
        (node for rank, node in ranked if rank == best_rank),
        key=lambda node: (node.qualified_name.casefold(), node.kind, node.id),
    )
    candidates = tuple(CandidateMatch(node.id, best_rank) for node in matches)
    return TargetResolution(
        selector=selector,
        status="matched" if len(candidates) == 1 else "ambiguous",
        candidates=candidates,
        omitted_candidates=0,
    )
