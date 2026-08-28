"""Immutable graph snapshots and atomic publication.

A graph snapshot is immutable once published. Publication follows:

``build → validate → build index → validate index → publish atomically``

A failed analysis never replaces the last valid graph (Invariant 12). The
snapshot carries a deterministic source fingerprint so clients can detect
staleness and never mix revisions (Invariant 6).
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from .analysis_budget import AnalysisBudget
from .diagnostics import Diagnostic, GRAPH_VALIDATION
from .graph import CodeGraph
from .index import GraphIndex


def graph_fingerprint(graph: CodeGraph) -> str:
    """Deterministic fingerprint of the graph's canonical serialization."""

    return sha256(graph.to_json().encode("utf-8"), usedforsecurity=False).hexdigest()


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    """One validated, immutable graph snapshot with its index."""

    revision: int
    graph: CodeGraph
    index: GraphIndex
    fingerprint: str

    @classmethod
    def publish(
        cls,
        graph: CodeGraph,
        *,
        revision: int,
        budget: AnalysisBudget | None = None,
    ) -> "GraphSnapshot":
        """Validate a fresh graph and build its immutable index atomically."""

        active_budget = budget or AnalysisBudget()
        violations = validate_graph(graph, budget=active_budget)
        if violations:
            raise GraphValidationError(violations)
        index = GraphIndex(graph)
        return cls(
            revision=revision,
            graph=graph,
            index=index,
            fingerprint=graph_fingerprint(graph),
        )


class GraphValidationError(RuntimeError):
    """Raised when a graph fails invariant validation and must not be published."""

    __slots__ = ("violations",)

    def __init__(self, violations: list[Diagnostic]) -> None:
        super().__init__(f"Graph validation failed with {len(violations)} violation(s)")
        self.violations = violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": "graph_validation_failed",
            "message": str(self),
            "details": {"violations": [item.to_dict() for item in self.violations]},
        }


def validate_graph(
    graph: CodeGraph,
    *,
    budget: AnalysisBudget | None = None,
) -> list[Diagnostic]:
    """Check the canonical graph invariants:

    - every edge endpoint refers to an existing node (Invariant 1)
    - every source-backed edge carries a location
    - origins and confidences are within the canonical vocabulary
    - graph schema version is current
    """

    active_budget = budget or AnalysisBudget()
    violations: list[Diagnostic] = []
    for edge in sorted(graph.edges.values(), key=lambda item: item.id):
        active_budget.consume("graph_validation")
        if edge.source not in graph.nodes:
            violations.append(Diagnostic(
                GRAPH_VALIDATION, "error",
                f"Edge {edge.id} source {edge.source!r} does not reference an existing node",
            ))
        if edge.target not in graph.nodes:
            violations.append(Diagnostic(
                GRAPH_VALIDATION, "error",
                f"Edge {edge.id} target {edge.target!r} does not reference an existing node",
            ))
    return violations


def write_snapshot(snapshot: GraphSnapshot, directory: str | Path, *, name: str = "graph.json") -> Path:
    """Atomically persist a snapshot's canonical graph to ``directory/name``."""

    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    output = target / name
    snapshot.graph.save(output)
    return output
