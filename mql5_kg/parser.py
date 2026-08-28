"""Tolerant structural extraction for MQL5 compilation units.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.

The parser tolerates incomplete, malformed, and partially edited source. It
pairs delimiters, locates type ranges and function bodies, extracts call sites
and includes, and recognizes MQL5-specific directives (``#define``,
``#property``, ``input``/``sinput``, ``#import`` blocks). It emits diagnostics
instead of crashing and consumes the analysis budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from .analysis_budget import AnalysisBudget
from .diagnostics import Diagnostic, UNMATCHED_DELIMITER
from .graph import SourceLocation
from .ir import CallSite, Declaration, IncludeRef, ParseResult
from .lexer import Token, tokenize

EVENT_HANDLERS = {
    "OnStart", "OnInit", "OnDeinit", "OnTick", "OnCalculate", "OnTimer", "OnTrade",
    "OnTradeTransaction", "OnBookEvent", "OnChartEvent", "OnTester", "OnTesterInit",
    "OnTesterPass", "OnTesterDeinit",
}

_CONTROL_WORDS = {"if", "for", "while", "switch", "return", "sizeof", "catch", "else"}
_POST_SIGNATURE = {"const", "override", "final", "virtual", "inline"}
_MODIFIER_WORDS = {
    "static", "virtual", "extern", "inline", "const", "override", "final",
    "public", "private", "protected", "template", "typename", "input", "sinput",
}
_NON_TYPE_WORDS = _CONTROL_WORDS | {
    "break", "case", "continue", "default", "delete", "do", "new", "public",
    "private", "protected", "throw", "true", "false",
}
_DECLARATION_FOLLOW = {";", "=", "[", ",", ")"}

# MQL5-specific directive patterns (matched against whole preprocessor lines)
_DEFINE_PATTERN = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)(?:\s+(.*))?$")
_PROPERTY_PATTERN = re.compile(r"^\s*#\s*property\s+(\w+)\s+(.+)$")
_IMPORT_OPEN_PATTERN = re.compile(r'^\s*#\s*import\s+"([^"]+)"\s*$')
_IMPORT_CLOSE_PATTERN = re.compile(r"^\s*#\s*import\s*$")


@dataclass(frozen=True, slots=True)
class _FunctionRange:
    declaration: Declaration
    open_paren: int
    close_paren: int
    owner_name: str | None


def _pairs(
    tokens: list[Token],
    opening: str,
    closing: str,
    file: str,
    budget: AnalysisBudget,
) -> tuple[dict[int, int], list[Diagnostic]]:
    stack: list[int] = []
    pairs: dict[int, int] = {}
    diagnostics: list[Diagnostic] = []
    for index, token in enumerate(tokens):
        budget.consume("parsing")
        if token.value == opening:
            stack.append(index)
        elif token.value == closing:
            if stack:
                start = stack.pop()
                pairs[start] = index
            else:
                diagnostics.append(Diagnostic(
                    UNMATCHED_DELIMITER, "warning", f"Unmatched {closing}",
                    SourceLocation(file, token.line, token.column),
                ))
    for index in stack:
        budget.consume("parsing")
        token = tokens[index]
        diagnostics.append(Diagnostic(
            UNMATCHED_DELIMITER, "warning", f"Unmatched {opening}",
            SourceLocation(file, token.line, token.column),
        ))
    return pairs, diagnostics


def _join_signature(tokens: list[Token], budget: AnalysisBudget) -> str:
    result = ""
    for token in tokens:
        budget.consume("parsing")
        if result and token.value not in {",", ")", "]", ";"} and result[-1] not in "([:.&*\"":
            result += " "
        result += token.value
    return result.strip()


def _argument_count(
    tokens: list[Token],
    start: int,
    end: int,
    budget: AnalysisBudget,
) -> int:
    if end <= start + 1:
        return 0
    depth = 0
    count = 1
    has_value = False
    for token in tokens[start + 1:end]:
        budget.consume("parsing")
        if token.value in {"(", "[", "{"}:
            depth += 1
        elif token.value in {")", "]", "}"}:
            depth = max(0, depth - 1)
        elif token.value == "," and depth == 0:
            count += 1
        elif token.value not in {"const", "&"}:
            has_value = True
    return count if has_value else 0


def _binding_at(
    tokens: list[Token],
    index: int,
    budget: AnalysisBudget,
) -> tuple[str, str] | None:
    """Return a simple C-like variable binding ending at ``index``."""

    if index <= 0 or index + 1 >= len(tokens):
        return None
    variable = tokens[index]
    if variable.kind != "identifier" or tokens[index + 1].value not in _DECLARATION_FOLLOW:
        return None
    cursor = index - 1
    while cursor >= 0 and tokens[cursor].value in {"&", "*"}:
        budget.consume("parsing")
        cursor -= 1
    if cursor < 0 or tokens[cursor].kind != "identifier":
        return None
    type_name = tokens[cursor].value
    if type_name in _NON_TYPE_WORDS:
        return None
    return variable.value, type_name


def _owner_at(
    type_ranges: list[tuple[int, int, str, str]],
    index: int,
    budget: AnalysisBudget,
) -> tuple[int, int, str, str] | None:
    for item in type_ranges:
        budget.consume("parsing")
        if item[0] < index < item[1]:
            return item
    return None


def _import_at(index: int, ranges: list[tuple[int, int, str]]) -> str | None:
    """Return the DLL name of the import block containing ``index``, if any."""

    for start, end, dll in ranges:
        if start <= index <= end:
            return dll
    return None


def _return_type_from_prefix(prefix: list[Token]) -> str | None:
    """Best-effort return type from the declaration prefix tokens.

    Strips modifiers and pointer/reference decorations. Returns ``None`` when
    the prefix carries no type information (e.g. constructors/destructors).
    """

    meaningful = [
        token.value
        for token in prefix
        if token.kind != "preprocessor"
        and token.value not in _MODIFIER_WORDS
        and token.value not in {"*", "&", "::", ":", "~", ".", "->"}
    ]
    if not meaningful:
        return None
    return " ".join(meaningful).strip()


def _extract_directives(
    tokens: list[Token],
    file: str,
    budget: AnalysisBudget,
) -> tuple[list[Declaration], list[tuple[int, int, str]]]:
    """Extract macro, property, and import-block declarations from preprocessor lines."""

    declarations: list[Declaration] = []
    import_ranges: list[tuple[int, int, str]] = []
    active_import: tuple[int, str] | None = None
    for index, token in enumerate(tokens):
        budget.consume("parsing")
        if token.kind != "preprocessor":
            if active_import is not None:
                # Preprocessor tokens end an import block; nothing else terminates it
                # until an argument-less #import line appears.
                continue
            continue
        value = token.value.strip()
        if active_import is not None:
            if _IMPORT_CLOSE_PATTERN.match(value):
                import_ranges.append((active_import[0], index, active_import[1]))
                active_import = None
            continue
        define = _DEFINE_PATTERN.match(value)
        if define:
            name = define.group(1)
            declaration = Declaration(
                kind="macro", name=name, qualified_name=name, signature=name,
                location=SourceLocation(file, token.line, token.column),
            )
            declarations.append(declaration)
            continue
        prop = _PROPERTY_PATTERN.match(value)
        if prop:
            key, prop_value = prop.group(1), prop.group(2).strip()
            qualified = f"property_{key}"
            declarations.append(Declaration(
                kind="property", name=qualified, qualified_name=qualified,
                signature=f"{key} {prop_value}",
                location=SourceLocation(file, token.line, token.column),
            ))
            continue
        opened = _IMPORT_OPEN_PATTERN.match(value)
        if opened:
            active_import = (index, opened.group(1))
            continue
    if active_import is not None:
        import_ranges.append((active_import[0], len(tokens) - 1, active_import[1]))
    return declarations, import_ranges


def _extract_input_variables(
    tokens: list[Token],
    file: str,
    budget: AnalysisBudget,
) -> list[Declaration]:
    """Extract ``input``/``sinput`` declarations at global scope."""

    declarations: list[Declaration] = []
    for index, token in enumerate(tokens[:-2]):
        budget.consume("parsing")
        if token.value not in {"input", "sinput"} or token.kind != "identifier":
            continue
        cursor = index + 1
        while cursor < len(tokens) and tokens[cursor].value in {"const", "static"}:
            budget.consume("parsing")
            cursor += 1
        if cursor + 1 >= len(tokens) or tokens[cursor].kind != "identifier":
            continue
        type_token = tokens[cursor]
        if type_token.value in _NON_TYPE_WORDS:
            continue
        name_token = tokens[cursor + 1]
        if name_token.kind != "identifier" or name_token.value in _NON_TYPE_WORDS:
            continue
        if cursor + 2 < len(tokens) and tokens[cursor + 2].value == "[":
            # array input: skip to matching close bracket
            cursor = cursor + 2
            while cursor < len(tokens) and tokens[cursor].value != "]":
                budget.consume("parsing")
                cursor += 1
        declarations.append(Declaration(
            kind="input_variable", name=name_token.value,
            qualified_name=name_token.value, signature=f"{type_token.value} {name_token.value}",
            location=SourceLocation(file, name_token.line, name_token.column),
        ))
    return declarations


def parse_source(
    text: str,
    file: str,
    *,
    budget: AnalysisBudget | None = None,
) -> ParseResult:
    active_budget = budget or AnalysisBudget()
    lexed = tokenize(text, file, budget=active_budget)
    tokens = lexed.tokens[:-1]
    result = ParseResult(file=file, diagnostics=list(lexed.diagnostics))
    parens, diagnostics = _pairs(tokens, "(", ")", file, active_budget)
    braces, brace_diagnostics = _pairs(tokens, "{", "}", file, active_budget)
    result.diagnostics.extend(diagnostics)
    result.diagnostics.extend(brace_diagnostics)

    include_pattern = re.compile(r"^\s*#\s*include\s*([<\"])([^\">]+)[>\"]")
    for token in tokens:
        active_budget.consume("parsing")
        if token.kind != "preprocessor":
            continue
        match = include_pattern.match(token.value)
        if match:
            result.includes.append(IncludeRef(
                target=match.group(2).strip(), system=match.group(1) == "<",
                location=SourceLocation(file, token.line, token.column),
            ))

    directive_declarations, import_ranges = _extract_directives(tokens, file, active_budget)
    result.declarations.extend(directive_declarations)

    type_ranges: list[tuple[int, int, str, str]] = []
    for index, token in enumerate(tokens[:-2]):
        active_budget.consume("parsing")
        if token.value not in {"class", "struct", "enum"} or tokens[index + 1].kind != "identifier":
            continue
        name_token = tokens[index + 1]
        open_index = None
        for cursor in range(index + 2, min(len(tokens), index + 20)):
            active_budget.consume("parsing")
            if tokens[cursor].value in {"{", ";"}:
                open_index = cursor
                break
        if open_index is None:
            continue
        body_end = braces.get(open_index) if tokens[open_index].value == "{" else None
        declaration = Declaration(
            kind=token.value, name=name_token.value, qualified_name=name_token.value,
            signature=name_token.value,
            location=SourceLocation(file, name_token.line, name_token.column),
            body_start=open_index if body_end is not None else None, body_end=body_end,
        )
        result.declarations.append(declaration)
        if body_end is not None:
            type_ranges.append((open_index, body_end, name_token.value, token.value))

    depth_at: list[int] = []
    depth = 0
    for token in tokens:
        active_budget.consume("parsing")
        depth_at.append(depth)
        if token.value == "{":
            depth += 1
        elif token.value == "}":
            depth = max(0, depth - 1)

    functions: list[_FunctionRange] = []
    for open_paren, close_paren in sorted(parens.items()):
        active_budget.consume("parsing")
        if open_paren == 0:
            continue
        name_index = open_paren - 1
        name_token = tokens[name_index]
        if name_token.kind != "identifier" or name_token.value in _CONTROL_WORDS:
            continue
        owner = _owner_at(type_ranges, open_paren, active_budget)
        expected_depth = 1 if owner else 0
        if depth_at[open_paren] != expected_depth:
            continue
        cursor = close_paren + 1
        while cursor < len(tokens) and tokens[cursor].value in _POST_SIGNATURE:
            active_budget.consume("parsing")
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor].value not in {"{", ";"}:
            continue
        if name_index > 0 and tokens[name_index - 1].value in {".", "->"}:
            continue

        boundary = name_index - 1
        while boundary >= 0 and tokens[boundary].value not in {";", "{", "}"}:
            active_budget.consume("parsing")
            boundary -= 1
        prefix = tokens[boundary + 1:name_index]
        if not prefix and name_token.value not in {owner[2] if owner else ""}:
            continue
        owner_name = owner[2] if owner else None
        qualified_name = f"{owner_name}::{name_token.value}" if owner_name else name_token.value
        if (
            owner_name
            and name_token.value == owner_name
            and name_index > 0
            and tokens[name_index - 1].value == "~"
        ):
            kind = "destructor"
        elif owner_name and name_token.value == owner_name:
            kind = "constructor"
        elif name_token.value in EVENT_HANDLERS and not owner:
            kind = "event_handler"
        elif owner:
            kind = "method"
        else:
            kind = "function"
        imported_from = _import_at(open_paren, import_ranges)
        if imported_from is not None:
            kind = "imported_symbol"
        body_start = cursor if tokens[cursor].value == "{" else None
        body_end = braces.get(cursor) if body_start is not None else None
        signature = f"{qualified_name}({_join_signature(tokens[open_paren + 1:close_paren], active_budget)})"
        if imported_from is not None:
            signature = f"{signature} #import {imported_from}"
        declaration = Declaration(
            kind=kind, name=name_token.value, qualified_name=qualified_name, signature=signature,
            location=SourceLocation(file, name_token.line, name_token.column),
            body_start=body_start, body_end=body_end,
            parameter_count=_argument_count(tokens, open_paren, close_paren, active_budget),
            return_type=_return_type_from_prefix(prefix),
        )
        functions.append(_FunctionRange(
            declaration=declaration,
            open_paren=open_paren,
            close_paren=close_paren,
            owner_name=owner_name,
        ))
        result.declarations.append(declaration)

    result.declarations.extend(
        _extract_input_variables(tokens, file, active_budget)
    )

    # Pre-compute token-to-function mapping for O(1) lookup (avoids the original
    # O(n*m) inside_function() bottleneck documented upstream in ANALYSIS.md).
    token_to_function: list[int | None] = [None] * len(tokens)
    for func_idx, item in enumerate(functions):
        declaration = item.declaration
        start = item.open_paren
        end = declaration.body_end if declaration.body_end is not None else item.close_paren
        for token_idx in range(start, min(end, len(tokens))):
            token_to_function[token_idx] = func_idx

    def inside_function_optimized(index: int) -> bool:
        if 0 <= index < len(token_to_function):
            return token_to_function[index] is not None
        return False

    outer_bindings: list[tuple[str | None, int, str, str]] = []
    for index in range(len(tokens)):
        active_budget.consume("parsing")
        if inside_function_optimized(index):
            continue
        binding = _binding_at(tokens, index, active_budget)
        if binding is None:
            continue
        owner = _owner_at(type_ranges, index, active_budget)
        outer_bindings.append((
            owner[2] if owner else None,
            index,
            binding[0],
            binding[1],
        ))

    # Precompute per-owner member bindings and unique receiver-type maps once so
    # the per-function binding resolution stays near-linear (avoids the original
    # O(functions x bindings) budget blowup documented upstream in ANALYSIS.md).
    global_bindings: list[tuple[int, str, str]] = []
    member_bindings_by_owner: dict[str, list[tuple[int, str, str]]] = {}
    for owner_name, index, name, type_name in outer_bindings:
        active_budget.consume("parsing")
        if owner_name is None:
            global_bindings.append((index, name, type_name))
        else:
            member_bindings_by_owner.setdefault(owner_name, []).append((index, name, type_name))

    def _unique_type_map(bindings: list[tuple[int, str, str]]) -> dict[str, str]:
        by_name: dict[str, set[str]] = {}
        for _, name, type_name in bindings:
            by_name.setdefault(name, set()).add(type_name)
        return {
            name: next(iter(types))
            for name, types in by_name.items()
            if len(types) == 1
        }

    global_unique_types = _unique_type_map(global_bindings)
    member_unique_types_by_owner = {
        owner: _unique_type_map(bindings)
        for owner, bindings in member_bindings_by_owner.items()
    }
    for function_range in functions:
        active_budget.consume("parsing")
        function = function_range.declaration
        if function.body_start is None:
            continue
        end = function.body_end if function.body_end is not None else len(tokens)
        parameter_bindings: list[tuple[int, str, str]] = []
        for index in range(function_range.open_paren + 1, function_range.close_paren):
            active_budget.consume("parsing")
            binding = _binding_at(tokens, index, active_budget)
            if binding is not None:
                parameter_bindings.append((index, *binding))
        local_bindings: list[tuple[int, str, str]] = []
        for index in range(function.body_start + 1, end):
            active_budget.consume("parsing")
            binding = _binding_at(tokens, index, active_budget)
            if binding is not None:
                local_bindings.append((index, *binding))
        owner_key = function_range.owner_name
        member_bindings = member_bindings_by_owner.get(owner_key, []) if owner_key else []
        member_unique_types = member_unique_types_by_owner.get(owner_key, {}) if owner_key else {}
        parameter_unique_types = _unique_type_map(parameter_bindings)
        cursor = function.body_start + 1
        while cursor < end - 1:
            active_budget.consume("parsing")
            token = tokens[cursor]
            if token.kind == "identifier" and tokens[cursor + 1].value == "(" and token.value not in _CONTROL_WORDS:
                close = parens.get(cursor + 1)
                if close is not None and close <= end:
                    qualifier = None
                    receiver_type = None
                    if cursor >= 2 and tokens[cursor - 1].value in {".", "->", "::"}:
                        qualifier = tokens[cursor - 2].value
                        if qualifier == "this":
                            receiver_type = function_range.owner_name
                        else:
                            local_matches: list[tuple[int, str]] = []
                            for index, name, type_name in local_bindings:
                                if name == qualifier and index < cursor:
                                    local_matches.append((index, type_name))
                            if local_matches:
                                receiver_type = local_matches[-1][1]
                            if receiver_type is None:
                                receiver_type = parameter_unique_types.get(qualifier)
                            if receiver_type is None:
                                receiver_type = member_unique_types.get(qualifier)
                            if receiver_type is None:
                                receiver_type = global_unique_types.get(qualifier)
                    result.calls.append(CallSite(
                        caller=function.qualified_name, name=token.value, qualifier=qualifier,
                        receiver_type=receiver_type,
                        argument_count=_argument_count(tokens, cursor + 1, close, active_budget),
                        location=SourceLocation(file, token.line, token.column),
                    ))
                    cursor += 1
            cursor += 1

    result.declarations.sort(key=lambda item: (item.location.line, item.location.column, item.qualified_name))
    result.calls.sort(key=lambda item: (item.location.line, item.location.column, item.name))
    return result
