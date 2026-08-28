"""Immutable sorted indexes derived from one canonical graph snapshot.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.

The index is read-only, deterministic, and never mutates the canonical graph.
All lookups (symbol, qualified name, file, relationships, callers, callees,
dependencies, diagnostics) resolve through these tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .diagnostics import Diagnostic
from .graph import CodeGraph, GraphEdge, GraphNode


def _node_key(node: GraphNode) -> tuple[str, str, str]:
    return (node.qualified_name.casefold(), node.kind, node.id)


def _diagnostic_key(
    diagnostic: Diagnostic,
) -> tuple[str, str, str, int, int, str]:
    location = diagnostic.location
    return (
        diagnostic.severity,
        diagnostic.code,
        location.file if location else "",
        location.line if location else 0,
        location.column if location else 0,
        diagnostic.message,
    )


@dataclass(frozen=True, slots=True, init=False)
class GraphIndex:
    """Read-only lookup and adjacency tables for a single ``CodeGraph``."""

    graph_schema_version: str
    source_fingerprint: str | None
    nodes: Mapping[str, GraphNode]
    edges: Mapping[str, GraphEdge]
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    nodes_by_name: Mapping[str, tuple[GraphNode, ...]]
    nodes_by_qualified_name: Mapping[str, tuple[GraphNode, ...]]
    incoming: Mapping[str, tuple[GraphEdge, ...]]
    outgoing: Mapping[str, tuple[GraphEdge, ...]]
    diagnostics: tuple[Diagnostic, ...]

    def __init__(self, graph: CodeGraph) -> None:
        ordered_nodes = tuple(sorted(graph.nodes.values(), key=_node_key))
        ordered_edges = tuple(sorted(graph.edges.values(), key=lambda edge: edge.id))
        by_name: dict[str, list[GraphNode]] = {}
        by_qualified: dict[str, list[GraphNode]] = {}
        incoming: dict[str, list[GraphEdge]] = {}
        outgoing: dict[str, list[GraphEdge]] = {}
        for node in ordered_nodes:
            by_name.setdefault(node.name.casefold(), []).append(node)
            by_qualified.setdefault(node.qualified_name.casefold(), []).append(node)
        for edge in ordered_edges:
            outgoing.setdefault(edge.source, []).append(edge)
            incoming.setdefault(edge.target, []).append(edge)

        object.__setattr__(self, "graph_schema_version", graph.schema_version)
        object.__setattr__(
            self, "source_fingerprint", graph.metadata.get("source_fingerprint")
        )
        object.__setattr__(
            self,
            "nodes",
            MappingProxyType({node.id: node for node in ordered_nodes}),
        )
        object.__setattr__(
            self,
            "edges",
            MappingProxyType({edge.id: edge for edge in ordered_edges}),
        )
        object.__setattr__(self, "node_ids", tuple(sorted(graph.nodes)))
        object.__setattr__(self, "edge_ids", tuple(sorted(graph.edges)))
        object.__setattr__(
            self,
            "nodes_by_name",
            MappingProxyType(
                {
                    key: tuple(sorted(values, key=_node_key))
                    for key, values in sorted(by_name.items())
                }
            ),
        )
        object.__setattr__(
            self,
            "nodes_by_qualified_name",
            MappingProxyType(
                {
                    key: tuple(sorted(values, key=_node_key))
                    for key, values in sorted(by_qualified.items())
                }
            ),
        )
        object.__setattr__(
            self,
            "incoming",
            MappingProxyType(
                {
                    key: tuple(sorted(values, key=lambda edge: edge.id))
                    for key, values in sorted(incoming.items())
                }
            ),
        )
        object.__setattr__(
            self,
            "outgoing",
            MappingProxyType(
                {
                    key: tuple(sorted(values, key=lambda edge: edge.id))
                    for key, values in sorted(outgoing.items())
                }
            ),
        )
        object.__setattr__(
            self, "diagnostics", tuple(sorted(graph.diagnostics, key=_diagnostic_key))
        )
