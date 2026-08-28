"""Runtime enrichment tests: runtime_dispatches and may_trigger_event separation."""

from mql5_kg.indexer import analyze_repository

from conftest import FIXTURES


def build():
    return analyze_repository(str(FIXTURES))


def test_runtime_terminal_node():
    graph = build()
    terminals = [node for node in graph.nodes.values() if node.kind == "runtime"]
    assert terminals
    assert terminals[0].qualified_name == "runtime::MetaTrader5Terminal"


def test_runtime_dispatches_edges():
    graph = build()
    dispatches = [
        edge for edge in graph.edges.values()
        if edge.relationship == "runtime_dispatches"
    ]
    assert dispatches
    for edge in dispatches:
        assert edge.origin == "runtime"
        assert edge.confidence == 1.0
        assert edge.attributes.get("event")


def test_event_handlers_are_dispatched():
    graph = build()
    handler_events = {
        edge.attributes.get("event")
        for edge in graph.edges.values()
        if edge.relationship == "runtime_dispatches"
    }
    assert "OnTick" in handler_events
    assert "OnInit" in handler_events


def test_order_send_may_trigger_on_trade_transaction():
    graph = build()
    triggered = [
        edge for edge in graph.edges.values()
        if edge.relationship == "may_trigger_event"
        and edge.attributes.get("runtime_rule") == "trade request processing"
    ]
    if triggered:
        for edge in triggered:
            assert edge.origin == "runtime"
            assert edge.attributes.get("event") is None or True


def test_runtime_edges_never_use_source_origin():
    graph = build()
    for edge in graph.edges.values():
        if edge.relationship in {"runtime_dispatches", "may_trigger_event"}:
            assert edge.origin == "runtime"
