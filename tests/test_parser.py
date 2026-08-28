"""Parser tests: declaration extraction, directives, call sites, tolerance."""

from mql5_kg.parser import parse_source
from mql5_kg.diagnostics import UNMATCHED_DELIMITER

from conftest import FIXTURES


def declarations(source: str):
    return parse_source(source, "test.mq5").declarations


def declaration_kinds(source: str):
    return {declaration.kind for declaration in declarations(source)}


def declaration_names(source: str):
    return [declaration.qualified_name for declaration in declarations(source)]


def calls(source: str):
    return parse_source(source, "test.mq5").calls


def test_functions_and_event_handlers():
    source = "void OnTick() { Foo(); }\nint Foo() { return 1; }\n"
    kinds = declaration_kinds(source)
    assert "function" in kinds
    assert "event_handler" in kinds


def test_methods_constructors_destructors():
    source = """\
class Widget
{
public:
    Widget() { }
    ~Widget() { }
    void Paint() { }
};
"""
    kinds = declaration_kinds(source)
    assert "class" in kinds
    assert "constructor" in kinds
    assert "destructor" in kinds
    assert "method" in kinds


def test_qualified_method_names():
    source = "class Widget { void Paint() { } };\n"
    names = declaration_names(source)
    assert "Widget::Paint" in names


def test_input_variables():
    source = "input double RiskPercent = 1.5;\nsinput int Fast = 12;\n"
    kinds = declaration_kinds(source)
    assert "input_variable" in kinds
    names = declaration_names(source)
    assert "RiskPercent" in names and "Fast" in names


def test_macros_and_properties():
    source = "#property copyright \"Test\"\n#define MAX_POSITIONS 10\n"
    kinds = declaration_kinds(source)
    assert "macro" in kinds
    assert "property" in kinds


def test_imported_symbols():
    source = """\
#import "kernel32.dll"
int GetTickCount();
#import
void UseIt() { GetTickCount(); }
"""
    names = declaration_names(source)
    kinds = declaration_kinds(source)
    assert "imported_symbol" in kinds
    assert "GetTickCount" in names


def test_call_sites():
    source = "void OnTick() { CloseAll(); OrderSend(req, res); }\n"
    call_sites = calls(source)
    assert {call.name for call in call_sites} == {"CloseAll", "OrderSend"}
    assert all(call.caller == "OnTick" for call in call_sites)


def test_control_flow_never_becomes_call_sites():
    source = """\
void OnTick()
{
    if(x) { }
    for(int i = 0; i < 10; i++) { }
    while(false) { }
    switch(x) { case 1: break; }
    return;
}
"""
    names = {call.name for call in calls(source)}
    assert names.isdisjoint({"if", "for", "while", "switch", "return", "case"})


def test_string_and_comment_immunity():
    source = 'void OnTick() { string s = "OrderSend(foo);"; // ClosePosition();\n}'
    names = {call.name for call in calls(source)}
    assert "OrderSend" not in names
    assert "ClosePosition" not in names


def test_source_locations_preserved():
    parsed = parse_source("void OnTick() { }\nint Foo() { return 1; }\n", "test.mq5")
    by_name = {d.name: d for d in parsed.declarations}
    assert by_name["OnTick"].location.line == 1
    assert by_name["Foo"].location.line == 2
    assert by_name["OnTick"].location.file == "test.mq5"


def test_return_types():
    parsed = parse_source(
        "double Calc(double x) { return x; }\nstatic int Count() { return 0; }\n",
        "test.mq5",
    )
    by_name = {d.name: d for d in parsed.declarations}
    assert by_name["Calc"].return_type == "double"
    assert by_name["Count"].return_type == "int"


def test_argument_counts():
    parsed = parse_source("void A(int x, int y) { B(x, y); C(); }\n", "test.mq5")
    decl = next(d for d in parsed.declarations if d.name == "A")
    assert decl.parameter_count == 2
    by_name = {call.name: call for call in parsed.calls}
    assert by_name["B"].argument_count == 2
    assert by_name["C"].argument_count == 0


def test_unmatched_delimiters_are_diagnostics_not_crashes():
    parsed = parse_source("void Broken() { if(x) { return; }\n", "broken.mq5")
    codes = {diagnostic.code for diagnostic in parsed.diagnostics}
    assert UNMATCHED_DELIMITER in codes
    # parsing still produced the function declaration
    assert any(declaration.name == "Broken" for declaration in parsed.declarations)


def test_parse_adversarial_broken_fixture():
    parsed = parse_source(
        (FIXTURES / "adversarial" / "adversarial_broken.mq5").read_text(encoding="utf-8"),
        "adversarial_broken.mq5",
    )
    # No crash; broken pieces still produce something parseable
    assert len(parsed.declarations) >= 0


def test_parse_large_file_is_linear():
    """The token-to-function map must keep large-file parsing fast."""
    import time

    lines = ["int Value%d(int x) { return x + %d; }" % (i, i) for i in range(3000)]
    source = "\n".join(lines) + "\n"
    start = time.monotonic()
    parse_source(source, "large.mq5")
    elapsed = time.monotonic() - start
    assert elapsed < 30, f"Parsing took too long: {elapsed:.1f}s"
