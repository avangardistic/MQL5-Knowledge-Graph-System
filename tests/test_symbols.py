"""Symbol model tests: deterministic identity rules and canonical kinds."""

from mql5_kg.symbols import (
    SYMBOL_KINDS,
    external_id,
    file_id,
    symbol_id,
)


def test_symbol_id_is_deterministic():
    first = symbol_id("function", "EA.mq5", "OnTick", "OnTick()")
    second = symbol_id("function", "EA.mq5", "OnTick", "OnTick()")
    assert first == second


def test_symbol_id_depends_on_semantic_content():
    base = symbol_id("function", "EA.mq5", "Foo", "Foo()")
    different_file = symbol_id("function", "Other.mq5", "Foo", "Foo()")
    different_kind = symbol_id("method", "EA.mq5", "Foo", "Foo()")
    different_signature = symbol_id("function", "EA.mq5", "Foo", "Foo(int)")
    assert len({base, different_file, different_kind, different_signature}) == 4


def test_symbol_id_is_not_line_dependent():
    a = symbol_id("function", "EA.mq5", "Foo", "Foo(int)")
    assert "line" not in a


def test_file_id_normalizes_case():
    assert file_id("EA.mq5") == file_id("ea.mq5")


def test_external_id():
    assert external_id("OrderSend").startswith("external:")


def test_all_required_kinds_present():
    for kind in (
        "project", "file", "class", "struct", "enum", "function", "method",
        "constructor", "destructor", "variable", "constant", "parameter",
        "property", "event_handler", "macro", "imported_symbol", "unknown",
    ):
        assert kind in SYMBOL_KINDS
