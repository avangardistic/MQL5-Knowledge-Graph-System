"""Lexer tests: token kinds, string/comment immunity, coordinates, recovery."""

from mql5_kg.lexer import tokenize
from mql5_kg.diagnostics import UNTERMINATED_COMMENT, UNTERMINATED_STRING


def token_values(text: str) -> list[str]:
    return [
        token.value
        for token in tokenize(text, "test.mq5").tokens
        if token.kind != "eof"
    ]


def test_identifiers_and_keywords_are_identifiers():
    values = token_values("int foo = 42;")
    assert values == ["int", "foo", "=", "42", ";"]


def test_string_literal_is_single_token():
    values = token_values('string s = "OrderSend(foo); ClosePosition(1);";')
    assert '"OrderSend(foo); ClosePosition(1);"' in values


def test_single_quoted_char_literal():
    values = token_values("char c = 'x';")
    assert "'x'" in values


def test_line_comment_is_skipped():
    values = token_values("// ClosePosition();\nvoid OnTick() {}")
    assert "ClosePosition" not in values


def test_block_comment_is_skipped():
    values = token_values("/* OrderSend(foo) */ void OnTick() {}")
    assert "OrderSend" not in values


def test_preprocessor_directive_token():
    result = tokenize('#include "x.mqh"\n', "test.mq5")
    assert result.tokens[0].kind == "preprocessor"
    assert result.tokens[0].value == '#include "x.mqh"'


def test_multi_character_operators():
    values = token_values("a <= b && c == d; e++; f += 2; g >>= 1;")
    for operator in ("<=", "&&", "==", "++", "+=", ">>="):
        assert operator in values


def test_source_coordinates():
    result = tokenize("int foo;\nint bar;", "test.mq5")
    by_value = {token.value: token for token in result.tokens if token.kind == "identifier"}
    assert by_value["foo"].line == 1
    assert by_value["foo"].column == 5
    assert by_value["bar"].line == 2
    assert by_value["bar"].column == 5


def test_offsets_are_monotonic():
    result = tokenize("int a;\nint b;\n", "test.mq5")
    offsets = [token.offset for token in result.tokens]
    assert offsets == sorted(offsets)


def test_unterminated_string_diagnostic():
    result = tokenize('string s = "oops;\n', "test.mq5")
    codes = [d.code for d in result.diagnostics]
    assert UNTERMINATED_STRING in codes


def test_unterminated_comment_diagnostic():
    result = tokenize("/* never closed\nint x;\n", "test.mq5")
    codes = [d.code for d in result.diagnostics]
    assert UNTERMINATED_COMMENT in codes


def test_numbers():
    values = token_values("1 1.5 0.01 1e-3 100LL 0x1F")
    assert "1" in values and "1.5" in values and "0.01" in values


def test_eof_token():
    result = tokenize("int x;", "test.mq5")
    assert result.tokens[-1].kind == "eof"
