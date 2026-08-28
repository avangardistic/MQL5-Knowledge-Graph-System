"""Resolver tests: include resolution, call resolution, ambiguity preservation."""

from pathlib import Path

import pytest

from mql5_kg.diagnostics import AMBIGUOUS_CALL, UNRESOLVED_CALL, UNRESOLVED_INCLUDE
from mql5_kg.indexer import analyze_repository
from mql5_kg.graph import CodeGraph

from conftest import FIXTURES, ADVERSARIAL


def graph_for(path: str | Path) -> CodeGraph:
    return analyze_repository(str(path))


def test_include_edges_resolved():
    graph = graph_for(FIXTURES)
    includes = [
        edge for edge in graph.edges.values()
        if edge.relationship == "includes"
        and graph.nodes[edge.source].qualified_name == "realistic_ea.mq5"
    ]
    assert includes
    for edge in includes:
        assert edge.origin == "resolved"
        assert edge.confidence == 1.0
        assert edge.location is not None


def test_unresolved_include_diagnostic():
    graph = graph_for(ADVERSARIAL)
    codes = {diagnostic.code for diagnostic in graph.diagnostics}
    assert UNRESOLVED_INCLUDE in codes
    unresolved = [
        edge for edge in graph.edges.values()
        if edge.relationship == "includes" and edge.confidence < 1.0
    ]
    assert unresolved


def test_include_traversal_guard():
    """Absolute includes and traversal must not escape the project root."""
    graph = graph_for(ADVERSARIAL)
    for edge in graph.edges.values():
        if edge.relationship == "includes":
            assert ".." not in edge.attributes.get("raw_target", "")


def test_circular_includes_are_safe(tmp_path):
    for name in ("circular_a.mqh", "circular_b.mqh"):
        (tmp_path / name).write_text(
            (ADVERSARIAL / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    graph = graph_for(tmp_path)
    includes = [edge for edge in graph.edges.values() if edge.relationship == "includes"]
    targets = {edge.target for edge in includes}
    assert "file:" in " ".join(targets)  # resolved to file nodes


def test_deep_include_chain_resolves(tmp_path):
    for name in ("deep_include_a.mqh", "deep_include_b.mqh", "deep_include_c.mqh"):
        (tmp_path / name).write_text(
            (ADVERSARIAL / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    graph = graph_for(tmp_path)
    includes = {
        (edge.attributes.get("raw_target"), edge.target)
        for edge in graph.edges.values()
        if edge.relationship == "includes"
    }
    assert any(raw == "deep_include_b.mqh" for raw, _ in includes)
    assert any(raw == "deep_include_c.mqh" for raw, _ in includes)


def test_external_nodes_for_unresolved_calls():
    graph = graph_for(FIXTURES)
    external = {node for node in graph.nodes.values() if node.kind == "external_function"}
    names = {node.name for node in external}
    assert "OrderSend" in names
    assert "PositionSelect" in names


def test_external_call_edges():
    graph = graph_for(FIXTURES)
    unresolved_edges = [
        edge for edge in graph.edges.values()
        if edge.relationship == "calls" and edge.origin == "extracted"
    ]
    assert unresolved_edges
    for edge in unresolved_edges:
        assert edge.attributes.get("resolution_status") == "unresolved"


def test_ambiguous_calls_preserved():
    source_root = Path(__file__).parent / "fixtures_ambig"
    source_root.mkdir(exist_ok=True)
    (source_root / "a.mq5").write_text(
        "void Foo() { Bar(1); }\ndouble Bar(int x) { return x; }\n", encoding="utf-8"
    )
    (source_root / "b.mq5").write_text(
        "double Bar(double x) { return x; }\n", encoding="utf-8"
    )
    try:
        graph = analyze_repository(str(source_root))
    finally:
        for path in source_root.iterdir():
            path.unlink()
        source_root.rmdir()
    ambiguous_edges = [
        edge for edge in graph.edges.values()
        if edge.relationship == "calls" and edge.attributes.get("ambiguous")
    ]
    assert ambiguous_edges, "Expected an ambiguous call edge"
    assert any(d.code == AMBIGUOUS_CALL for d in graph.diagnostics)


def test_resolved_calls_have_evidence():
    graph = graph_for(FIXTURES)
    resolved = [
        edge for edge in graph.edges.values()
        if edge.relationship == "calls" and edge.origin == "resolved"
    ]
    assert resolved
    for edge in resolved:
        assert edge.location is not None
        assert edge.confidence == 1.0
        assert edge.attributes.get("resolution_status") == "resolved"


def test_class_method_scope_preference():
    """Class-qualified calls resolve to class members, not globals."""
    from mql5_kg.parser import parse_source
    from mql5_kg.resolver import ParsedUnit, build_graph
    from pathlib import Path
    from mql5_kg.indexer import DEFAULT_EXCLUDED_DIRECTORIES

    source = """\
class Engine
{
public:
    void Run() { Start(); }
    void Start() { }
};

void Start() { }
"""
    unit = ParsedUnit(Path("engine.mq5").resolve(), "engine.mq5", parse_source(source, "engine.mq5"))
    graph, _ = build_graph([unit], Path(".").resolve(), [], "fp-test")
    run_node = next(node for node in graph.nodes.values() if node.qualified_name == "Engine::Run")
    start_nodes = [node for node in graph.nodes.values() if node.qualified_name == "Engine::Start"]
    assert start_nodes, "Engine::Start method not extracted"
    calls = [
        edge for edge in graph.edges.values()
        if edge.relationship == "calls" and edge.source == run_node.id
    ]
    assert calls, "Expected Engine::Run to call something"
    assert calls[0].target == start_nodes[0].id, "Unqualified call resolved to global instead of class scope"
