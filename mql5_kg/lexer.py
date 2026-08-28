"""A recovery-oriented MQL5 tokenizer with precise source coordinates.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.

The lexer never interprets text inside strings or comments as executable
syntax, so ``string x = "OrderSend(foo)";`` and ``// ClosePosition();`` cannot
create relationships.
"""

from __future__ import annotations

from dataclasses import dataclass

from .analysis_budget import AnalysisBudget
from .diagnostics import Diagnostic, UNTERMINATED_COMMENT, UNTERMINATED_STRING
from .graph import SourceLocation


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    value: str
    line: int
    column: int
    offset: int


@dataclass(slots=True)
class LexResult:
    tokens: list[Token]
    diagnostics: list[Diagnostic]


_MULTI_OPERATORS = (
    "<<=", ">>=", "::", "->", "++", "--", "==", "!=", "<=", ">=", "&&", "||",
    "+=", "-=", "*=", "/=", "%=", "<<", ">>", "&=", "|=", "^=",
)


def tokenize(
    text: str,
    file: str,
    *,
    budget: AnalysisBudget | None = None,
) -> LexResult:
    active_budget = budget or AnalysisBudget()
    tokens: list[Token] = []
    diagnostics: list[Diagnostic] = []
    index = 0
    line = 1
    column = 1
    length = len(text)
    line_has_content = False

    def advance(value: str, *, content: bool = True) -> None:
        nonlocal line, column, line_has_content
        newlines = value.count("\n")
        if newlines:
            line += newlines
            suffix = value.rsplit("\n", 1)[-1]
            column = len(suffix) + 1
            line_has_content = content and bool(suffix.strip())
        else:
            column += len(value)
            line_has_content = line_has_content or content

    while index < length:
        active_budget.consume("lexing")
        char = text[index]
        if char.isspace():
            start = index
            while index < length and text[index].isspace():
                if index != start:
                    active_budget.consume("lexing")
                index += 1
            advance(text[start:index], content=False)
            continue

        start_line, start_column, start_offset = line, column, index
        at_line_start = not line_has_content
        if char == "#" and at_line_start:
            end = index
            while end < length and text[end] != "\n":
                if end != index:
                    active_budget.consume("lexing")
                end += 1
            value = text[index:end]
            tokens.append(Token("preprocessor", value, line, column, index))
            index = end
            advance(value)
            continue

        if text.startswith("//", index):
            end = index
            while end < length and text[end] != "\n":
                if end != index:
                    active_budget.consume("lexing")
                end += 1
            advance(text[index:end])
            index = end
            continue

        if text.startswith("/*", index):
            end = index
            closed = False
            while end < length:
                if end != index:
                    active_budget.consume("lexing")
                if text.startswith("*/", end):
                    active_budget.consume("lexing")
                    end += 2
                    closed = True
                    break
                end += 1
            if not closed:
                value = text[index:length]
                diagnostics.append(Diagnostic(
                    UNTERMINATED_COMMENT, "warning", "Unterminated block comment",
                    SourceLocation(file, start_line, start_column),
                ))
                advance(value)
                index = length
            else:
                value = text[index:end]
                advance(value)
                index = end
            continue

        if char in {'"', "'"}:
            quote = char
            index += 1
            escaped = False
            while index < length:
                active_budget.consume("lexing")
                current = text[index]
                index += 1
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == quote:
                    break
                elif current == "\n":
                    break
            value = text[start_offset:index]
            if not value.endswith(quote):
                diagnostics.append(Diagnostic(
                    UNTERMINATED_STRING, "warning", "Unterminated string or character literal",
                    SourceLocation(file, start_line, start_column),
                ))
            tokens.append(Token("string", value, start_line, start_column, start_offset))
            advance(value)
            continue

        if char == "_" or char.isalpha():
            index += 1
            while index < length and (text[index] == "_" or text[index].isalnum()):
                active_budget.consume("lexing")
                index += 1
            value = text[start_offset:index]
            tokens.append(Token("identifier", value, line, column, start_offset))
            advance(value)
            continue

        if char.isdigit() or (char == "." and index + 1 < length and text[index + 1].isdigit()):
            index += 1
            while index < length and (text[index].isalnum() or text[index] in "._+-"):
                active_budget.consume("lexing")
                if text[index] in "+-" and text[index - 1] not in "eE":
                    break
                index += 1
            value = text[start_offset:index]
            tokens.append(Token("number", value, line, column, start_offset))
            advance(value)
            continue

        operator = next((item for item in _MULTI_OPERATORS if text.startswith(item, index)), None)
        value = operator or char
        for _ in value[1:]:
            active_budget.consume("lexing")
        tokens.append(Token("symbol", value, line, column, index))
        index += len(value)
        advance(value)

    tokens.append(Token("eof", "", line, column, length))
    return LexResult(tokens, diagnostics)
