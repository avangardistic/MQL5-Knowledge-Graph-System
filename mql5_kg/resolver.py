"""Repository-wide MQL5 include and call resolution.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.

Resolution preserves states: ``resolved``, ``ambiguous`` (every candidate kept
and reported), and ``unresolved`` (external/unknown targets become
``external_function`` nodes). Never convert ambiguity into certainty.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable

from .analysis_budget import AnalysisBudget
from .diagnostics import Diagnostic, AMBIGUOUS_CALL, UNRESOLVED_CALL, UNRESOLVED_INCLUDE
from .evidence import (
    CONFIDENCE_AMBIGUOUS,
    CONFIDENCE_EXACT,
    CONFIDENCE_UNRESOLVED,
    CONFIDENCE_UNRESOLVED_INCLUDE,
)
from .graph import CodeGraph, GraphNode, SourceLocation
from .ir import Declaration, ParseResult
from .scopes import STATE_AMBIGUOUS, STATE_RESOLVED, STATE_UNRESOLVED
from .symbols import external_id, file_id, symbol_id
from .version import __version__


@dataclass(frozen=True, slots=True)
class ParsedUnit:
    absolute_path: Path
    relative_path: str
    parsed: ParseResult


def _external_node(graph: CodeGraph, name: str) -> GraphNode:
    node = GraphNode(
        id=external_id(name), kind="external_function", name=name,
        qualified_name=f"MQL5::{name}", attributes={"external": True},
    )
    return graph.add_node(node)


def _resolve_include(
    unit: ParsedUnit,
    target: str,
    system: bool,
    root: Path,
    include_roots: Iterable[Path],
    budget: AnalysisBudget | None = None,
) -> Path | None:
    active_budget = budget or AnalysisBudget()
    normalized = target.replace("\\", "/")
    windows_target = PureWindowsPath(target)
    if (
        not normalized
        or PurePosixPath(normalized).is_absolute()
        or windows_target.is_absolute()
        or bool(windows_target.drive)
    ):
        return None
    resolved_root = root.resolve()
    resolved_include_roots: list[Path] = []
    for path in include_roots:
        active_budget.consume("resolution")
        resolved_include_roots.append(path.resolve())
    resolved_include_roots = tuple(resolved_include_roots)
    approved_roots = (resolved_root, *resolved_include_roots)
    candidates: list[Path] = []
    if not system:
        candidates.append(unit.absolute_path.parent / normalized)
    candidates.append(resolved_root / normalized)
    for path in resolved_include_roots:
        active_budget.consume("resolution")
        candidates.append(path / normalized)
    for candidate in candidates:
        active_budget.consume("resolution")
        resolved_candidate = candidate.resolve()
        inside_approved_root = False
        for approved in approved_roots:
            active_budget.consume("resolution")
            if (
                resolved_candidate == approved
                or resolved_candidate.is_relative_to(approved)
            ):
                inside_approved_root = True
                break
        if not inside_approved_root:
            continue
        if resolved_candidate.is_file():
            return resolved_candidate
    return None


def build_graph(
    units: list[ParsedUnit],
    root: Path,
    include_roots: list[Path],
    fingerprint: str,
    *,
    budget: AnalysisBudget | None = None,
) -> tuple[CodeGraph, dict[tuple[str, str, str], str]]:
    active_budget = budget or AnalysisBudget()
    graph = CodeGraph({
        "root": root.as_posix(), "source_fingerprint": fingerprint,
        "file_count": len(units), "tool_version": __version__,
    })
    absolute_to_relative: dict[Path, str] = {}
    for unit in units:
        active_budget.consume("resolution")
        absolute_to_relative[unit.absolute_path.resolve()] = unit.relative_path
    declaration_ids: dict[tuple[str, str, str], str] = {}
    by_short_name: dict[str, list[tuple[ParsedUnit, Declaration, str]]] = {}
    by_qualified_name: dict[str, list[tuple[ParsedUnit, Declaration, str]]] = {}
    reported_unresolved_calls: set[str] = set()
    reported_ambiguous_calls: set[tuple[str, tuple[str, ...]]] = set()

    for unit in units:
        active_budget.consume("resolution")
        file_node = GraphNode(
            id=file_id(unit.relative_path), kind="file", name=Path(unit.relative_path).name,
            qualified_name=unit.relative_path, attributes={"extension": unit.absolute_path.suffix.lower()},
        )
        graph.add_node(file_node)
        for diagnostic in unit.parsed.diagnostics:
            active_budget.consume("resolution")
            graph.add_diagnostic(diagnostic)
        for declaration in unit.parsed.declarations:
            active_budget.consume("resolution")
            node_id = symbol_id(
                declaration.kind, unit.relative_path, declaration.qualified_name,
                declaration.signature,
            )
            declaration_ids[(unit.relative_path, declaration.qualified_name, declaration.signature)] = node_id
            attributes: dict[str, object] = {
                "signature": declaration.signature,
                "parameter_count": declaration.parameter_count,
                "return_type": declaration.return_type,
            }
            if declaration.kind == "imported_symbol" and " #import " in declaration.signature:
                attributes["imported_from"] = declaration.signature.split(" #import ", 1)[1]
            node = GraphNode(
                id=node_id, kind=declaration.kind, name=declaration.name,
                qualified_name=declaration.qualified_name, location=declaration.location,
                attributes=attributes,
            )
            graph.add_node(node)
            graph.add_edge(file_node.id, node.id, "defines", "extracted", 1.0, declaration.location)
            entry = (unit, declaration, node_id)
            by_short_name.setdefault(declaration.name, []).append(entry)
            by_qualified_name.setdefault(declaration.qualified_name, []).append(entry)

    for unit in units:
        active_budget.consume("resolution")
        source_file_id = file_id(unit.relative_path)
        for include in unit.parsed.includes:
            active_budget.consume("resolution")
            resolved = _resolve_include(
                unit,
                include.target,
                include.system,
                root,
                include_roots,
                active_budget,
            )
            if resolved is None:
                target_node = graph.add_node(GraphNode(
                    id=stable_unresolved_file_id(include.target), kind="file",
                    name=Path(include.target).name, qualified_name=include.target,
                    attributes={"external": True, "unresolved": True},
                ))
                graph.add_diagnostic(Diagnostic(
                    UNRESOLVED_INCLUDE, "warning", f"Unable to resolve include {include.target!r}",
                    include.location,
                ))
                confidence = CONFIDENCE_UNRESOLVED_INCLUDE
            else:
                relative = absolute_to_relative.get(resolved)
                if relative is None:
                    try:
                        relative = resolved.relative_to(root).as_posix()
                    except ValueError:
                        relative = resolved.as_posix()
                target_node = graph.add_node(GraphNode(
                    id=file_id(relative), kind="file", name=resolved.name, qualified_name=relative,
                    attributes={"external": resolved not in absolute_to_relative},
                ))
                confidence = CONFIDENCE_EXACT
            graph.add_edge(source_file_id, target_node.id, "includes", "resolved", confidence,
                           include.location, {"raw_target": include.target, "system": include.system})

        caller_entries: dict[str, str] = {}
        for entries in by_short_name.values():
            active_budget.consume("resolution")
            for candidate_unit, declaration, node_id in entries:
                active_budget.consume("resolution")
                if candidate_unit.relative_path == unit.relative_path:
                    caller_entries[declaration.qualified_name] = node_id
        for call in unit.parsed.calls:
            active_budget.consume("resolution")
            caller_id = caller_entries.get(call.caller)
            if caller_id is None:
                continue
            candidates: list[tuple[ParsedUnit, Declaration, str]] = []
            for item in by_short_name.get(call.name, []):
                active_budget.consume("resolution")
                candidates.append(item)
            same_arity: list[tuple[ParsedUnit, Declaration, str]] = []
            for item in candidates:
                active_budget.consume("resolution")
                if item[1].parameter_count == call.argument_count:
                    same_arity.append(item)
            receiver_type = call.receiver_type
            if receiver_type is None and call.qualifier:
                qualifier_members: list[tuple[ParsedUnit, Declaration, str]] = []
                for item in candidates:
                    active_budget.consume("resolution")
                    if item[1].qualified_name.rpartition("::")[0] == call.qualifier:
                        qualifier_members.append(item)
                if qualifier_members:
                    receiver_type = call.qualifier
            if receiver_type is not None:
                receiver_members: list[tuple[ParsedUnit, Declaration, str]] = []
                for item in candidates:
                    active_budget.consume("resolution")
                    if item[1].qualified_name.rpartition("::")[0] == receiver_type:
                        receiver_members.append(item)
                receiver_arity: list[tuple[ParsedUnit, Declaration, str]] = []
                for item in receiver_members:
                    active_budget.consume("resolution")
                    if item[1].parameter_count == call.argument_count:
                        receiver_arity.append(item)
                selected = receiver_arity or receiver_members
            else:
                same_scope: list[tuple[ParsedUnit, Declaration, str]] = []
                for item in candidates:
                    active_budget.consume("resolution")
                    if (
                        item[1].qualified_name.rpartition("::")[0]
                        == call.caller.rpartition("::")[0]
                        and item[1].parameter_count == call.argument_count
                    ):
                        same_scope.append(item)
                selected = same_scope or same_arity or candidates
            if not selected:
                target = _external_node(graph, call.name)
                graph.add_edge(caller_id, target.id, "calls", "extracted", CONFIDENCE_UNRESOLVED,
                               call.location, {
                                   "argument_count": call.argument_count,
                                   "qualifier": call.qualifier,
                                   "resolution_status": STATE_UNRESOLVED,
                               })
                if call.name not in reported_unresolved_calls:
                    reported_unresolved_calls.add(call.name)
                    graph.add_diagnostic(Diagnostic(
                        UNRESOLVED_CALL, "info",
                        f"Call target {call.name!r} is external or unresolved; additional sites are grouped",
                        call.location,
                    ))
            else:
                if len(selected) == 1:
                    confidence = CONFIDENCE_EXACT
                    status = STATE_RESOLVED
                else:
                    confidence = CONFIDENCE_AMBIGUOUS
                    status = STATE_AMBIGUOUS
                if len(selected) > 1:
                    ambiguity_key = (call.name, tuple(sorted(item[2] for item in selected)))
                    if ambiguity_key not in reported_ambiguous_calls:
                        reported_ambiguous_calls.add(ambiguity_key)
                        graph.add_diagnostic(Diagnostic(
                            AMBIGUOUS_CALL, "warning",
                            f"Call {call.name!r} has {len(selected)} candidate targets; additional sites are grouped",
                            call.location,
                        ))
                for _, _, target_id in selected:
                    active_budget.consume("resolution")
                    graph.add_edge(caller_id, target_id, "calls", "resolved", confidence,
                                   call.location, {
                                       "argument_count": call.argument_count,
                                       "qualifier": call.qualifier,
                                       "resolution_status": status,
                                       "ambiguous": status == STATE_AMBIGUOUS,
                                   })
    return graph, declaration_ids


def stable_unresolved_file_id(target: str) -> str:
    """Deterministic node identity for includes that could not be resolved."""

    from .graph import stable_id

    return stable_id("unresolved-file", target.casefold())
