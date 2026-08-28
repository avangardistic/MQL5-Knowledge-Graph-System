"""Golden graph regression tests: deterministic outputs over fixed fixtures."""

from mql5_kg.graph import CodeGraph
from mql5_kg.indexer import analyze_repository
from mql5_kg.snapshots import GraphSnapshot, validate_graph

from conftest import FIXTURES


def test_graph_identity_is_stable():
    """Same source + same configuration ⇒ identical graph JSON."""
    first = analyze_repository(str(FIXTURES))
    second = analyze_repository(str(FIXTURES))
    assert first.to_json() == second.to_json()


def test_source_fingerprint_stable():
    first = analyze_repository(str(FIXTURES))
    second = analyze_repository(str(FIXTURES))
    assert first.metadata["source_fingerprint"] == second.metadata["source_fingerprint"]


def test_golden_symbol_counts():
    graph = analyze_repository(str(FIXTURES))
    kinds = {}
    for node in graph.nodes.values():
        kinds[node.kind] = kinds.get(node.kind, 0) + 1
    assert kinds["file"] >= 5
    assert kinds["event_handler"] >= 4
    assert kinds["input_variable"] >= 5
    assert kinds["macro"] >= 2
    assert kinds["property"] >= 2
    assert kinds["external_function"] > 0
    assert kinds["runtime"] == 1


def test_golden_relationship_invariants():
    graph = analyze_repository(str(FIXTURES))
    relationships = {edge.relationship for edge in graph.edges.values()}
    assert {"calls", "includes", "defines", "runtime_dispatches"} <= relationships


def test_every_edge_endpoint_exists():
    graph = analyze_repository(str(FIXTURES))
    assert validate_graph(graph) == []


def test_no_control_flow_call_targets():
    graph = analyze_repository(str(FIXTURES))
    keywords = {"if", "for", "while", "switch", "else", "case", "default", "do"}
    call_targets = {
        graph.nodes[edge.target].name
        for edge in graph.edges.values()
        if edge.relationship == "calls" and edge.target in graph.nodes
    }
    assert call_targets.isdisjoint(keywords)


def test_source_backed_edges_have_evidence():
    graph = analyze_repository(str(FIXTURES))
    for edge in graph.edges.values():
        if edge.origin in {"extracted", "resolved"} and edge.relationship in {"calls", "includes", "defines"}:
            assert edge.location is not None, f"missing location on {edge.id}"


def test_ambiguous_never_marked_resolved():
    graph = analyze_repository(str(FIXTURES))
    for edge in graph.edges.values():
        if edge.relationship == "calls":
            status = edge.attributes.get("resolution_status")
            if edge.attributes.get("ambiguous"):
                assert status == "ambiguous"
            if status == "ambiguous":
                assert edge.attributes.get("ambiguous") is True


def test_serialization_round_trip_preserves_everything(tmp_path):
    graph = analyze_repository(str(FIXTURES))
    snapshot = GraphSnapshot.publish(graph, revision=1)
    path = tmp_path / "golden.json"
    graph.save(path)
    reloaded = CodeGraph.load(path)
    assert reloaded.to_json() == graph.to_json()
    assert len(reloaded.nodes) == len(graph.nodes)
    assert len(reloaded.edges) == len(graph.edges)
    assert len(reloaded.diagnostics) == len(graph.diagnostics)
