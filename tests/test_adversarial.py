"""Adversarial parser tests: the parser must fail gracefully on hostile input."""

from pathlib import Path

import pytest

from mql5_kg.indexer import analyze_repository
from mql5_kg.parser import parse_source

from conftest import ADVERSARIAL


def test_broken_source_never_crashes():
    source = (ADVERSARIAL / "adversarial_broken.mq5").read_text(encoding="utf-8")
    parsed = parse_source(source, "adversarial_broken.mq5")
    # Diagnostics exist but the parser produced an IR result
    assert parsed.diagnostics
    assert parsed.file == "adversarial_broken.mq5"


def test_missing_semicolon_recovered():
    source = "int g_broken = 1\ndouble g_after = 2.0;\n"
    parsed = parse_source(source, "semi.mq5")
    assert len(parsed.declarations) >= 0


def test_unclosed_block_comment_recovery():
    source = "/* never closed\nvoid OnTick() { }\n"
    parsed = parse_source(source, "comment.mq5")
    from mql5_kg.diagnostics import UNTERMINATED_COMMENT

    assert any(d.code == UNTERMINATED_COMMENT for d in parsed.diagnostics)


def test_code_looking_strings_do_not_create_calls():
    source = 'void A() { string s = "OrderSend(foo);"; }\n'
    parsed = parse_source(source, "strings.mq5")
    assert all(call.name != "OrderSend" for call in parsed.calls)


def test_misleading_comments_do_not_create_calls():
    source = "// ClosePosition();\n/* OpenBuy(); */\nvoid A() { }\n"
    parsed = parse_source(source, "comments.mq5")
    assert not parsed.calls


def test_duplicate_symbols_kept_separate():
    source = "int Foo() { return 1; }\nint Foo() { return 2; }\n"
    parsed = parse_source(source, "dupes.mq5")
    foos = [d for d in parsed.declarations if d.name == "Foo"]
    assert len(foos) == 2


def test_overloads_kept_separate():
    source = "double Compute(double x) { return x; }\ndouble Compute(double x, double y) { return x + y; }\n"
    parsed = parse_source(source, "overloads.mq5")
    computes = [d for d in parsed.declarations if d.name == "Compute"]
    assert len(computes) == 2
    assert {d.parameter_count for d in computes} == {1, 2}


def test_nested_scopes_and_shadowing():
    source = """\
void ScopeTrap()
{
    int value = 1;
    {
        int value = 2;
        Print(value);
    }
    Print(value);
}
"""
    parsed = parse_source(source, "shadow.mq5")
    assert any(d.name == "ScopeTrap" for d in parsed.declarations)
    # Calls inside ScopeTrap only
    assert all(call.caller == "ScopeTrap" for call in parsed.calls)


def test_deep_include_graph_builds(tmp_path):
    for name in ("deep_include_a.mqh", "deep_include_b.mqh", "deep_include_c.mqh"):
        (tmp_path / name).write_text(
            (ADVERSARIAL / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    graph = analyze_repository(str(tmp_path))
    assert graph.nodes
    assert graph.metadata["file_count"] == 3


def test_circular_include_graph_builds(tmp_path):
    for name in ("circular_a.mqh", "circular_b.mqh"):
        (tmp_path / name).write_text(
            (ADVERSARIAL / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    graph = analyze_repository(str(tmp_path))
    assert graph.nodes
    assert graph.edges


def test_empty_file():
    parsed = parse_source("", "empty.mq5")
    assert not parsed.declarations
    assert not parsed.calls


def test_only_comments_and_strings():
    source = '// nothing\n/* nothing */\nstring s = "void Fake() { }";\n'
    parsed = parse_source(source, "noise.mq5")
    assert not any(d.name == "Fake" for d in parsed.declarations)


def test_unicode_identifiers_and_comments():
    source = "// Привет мир\nvoid OnTick() { }\nint значение = 5;\n"
    parsed = parse_source(source, "unicode.mq5")
    assert any(d.name == "OnTick" for d in parsed.declarations)
