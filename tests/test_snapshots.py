"""Snapshot tests: immutable publication, invariant validation, atomic failure."""

import pytest

from mql5_kg.graph import CodeGraph, GraphEdge, GraphNode, SourceLocation
from mql5_kg.indexer import analyze_repository
from mql5_kg.snapshots import GraphSnapshot, GraphValidationError, graph_fingerprint, write_snapshot

from conftest import FIXTURES


def test_publish_creates_snapshot():
    graph = analyze_repository(str(FIXTURES))
    snapshot = GraphSnapshot.publish(graph, revision=1)
    assert snapshot.revision == 1
    assert snapshot.fingerprint == graph_fingerprint(graph)
    assert snapshot.index is not None
    assert len(snapshot.index.nodes) == len(graph.nodes)


def test_dangling_edge_rejected():
    graph = CodeGraph({"root": "."})
    node = GraphNode(
        id="symbol:1", kind="function", name="Foo", qualified_name="Foo",
        location=SourceLocation("a.mq5", 1, 1),
    )
    graph.add_node(node)
    graph.add_edge(node.id, "symbol:does-not-exist", "calls", "extracted", 1.0,
                   SourceLocation("a.mq5", 2, 1))
    with pytest.raises(GraphValidationError):
        GraphSnapshot.publish(graph, revision=1)


def test_validation_error_is_machine_readable():
    graph = CodeGraph({"root": "."})
    graph.add_edge("missing-source", "missing-target", "calls", "extracted", 1.0)
    with pytest.raises(GraphValidationError) as exc_info:
        GraphSnapshot.publish(graph, revision=1)
    payload = exc_info.value.to_dict()
    assert payload["code"] == "graph_validation_failed"
    assert len(payload["details"]["violations"]) >= 2


def test_write_snapshot_persists(tmp_path):
    graph = analyze_repository(str(FIXTURES))
    snapshot = GraphSnapshot.publish(graph, revision=2)
    output = write_snapshot(snapshot, str(tmp_path))
    assert output.exists()
    reloaded = CodeGraph.load(output)
    assert reloaded.to_json() == graph.to_json()
