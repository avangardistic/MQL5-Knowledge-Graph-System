"""GraphIndex tests: immutable sorted indexes and deterministic lookups."""

from mql5_kg.index import GraphIndex
from mql5_kg.indexer import analyze_repository

from conftest import FIXTURES


def test_index_is_deterministic():
    graph = analyze_repository(str(FIXTURES))
    index_a = GraphIndex(graph)
    index_b = GraphIndex(graph)
    assert index_a.node_ids == index_b.node_ids
    assert index_a.edge_ids == index_b.edge_ids


def test_name_lookup():
    graph = analyze_repository(str(FIXTURES))
    index = GraphIndex(graph)
    matches = index.nodes_by_name.get("ontick", ())
    assert matches
    assert all(node.name == "OnTick" for node in matches)


def test_qualified_name_lookup():
    graph = analyze_repository(str(FIXTURES))
    index = GraphIndex(graph)
    assert index.nodes_by_qualified_name


def test_incoming_outgoing_adjacency():
    graph = analyze_repository(str(FIXTURES))
    index = GraphIndex(graph)
    for node_id in index.node_ids:
        incoming = index.incoming.get(node_id, ())
        outgoing = index.outgoing.get(node_id, ())
        for edge in incoming:
            assert edge.target == node_id
        for edge in outgoing:
            assert edge.source == node_id


def test_diagnostics_sorted():
    graph = analyze_repository(str(FIXTURES))
    index = GraphIndex(graph)
    # Canonical sort key is (severity, code, file, line, column, message)
    expected = sorted(
        index.diagnostics,
        key=lambda d: (
            d.severity,
            d.code,
            d.location.file if d.location else "",
            d.location.line if d.location else 0,
            d.location.column if d.location else 0,
            d.message,
        ),
    )
    assert list(index.diagnostics) == expected


def test_index_does_not_mutate_graph():
    graph = analyze_repository(str(FIXTURES))
    before = graph.to_json()
    GraphIndex(graph)
    assert graph.to_json() == before
