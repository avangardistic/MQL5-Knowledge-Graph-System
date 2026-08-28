"""Repository discovery and end-to-end MQL5 graph construction.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable

from .analysis_budget import AnalysisBudget
from .diagnostics import Diagnostic, DECODE_RECOVERY
from .graph import CodeGraph, SourceLocation
from .parser import parse_source
from .resolver import ParsedUnit, build_graph
from .runtime import enrich_runtime


DEFAULT_EXCLUDED_DIRECTORIES = {".git", ".gitnexus", "graphify-out", "build", "dist", "__pycache__"}


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """Deterministic identity and latest modification time for discovered MQL5 source."""

    fingerprint: str
    file_count: int
    latest_mtime_ns: int


def discover_sources(
    root: Path,
    excluded: Iterable[str] = (),
    *,
    budget: AnalysisBudget | None = None,
) -> list[Path]:
    root = root.resolve()
    active_budget = budget or AnalysisBudget()
    excluded_names = DEFAULT_EXCLUDED_DIRECTORIES | set(excluded)
    sources: set[Path] = set()
    for path in root.rglob("*"):
        active_budget.consume("source_discovery")
        if path.suffix.lower() not in {".mq5", ".mqh"}:
            continue
        try:
            lexical_relative = path.relative_to(root)
            resolved = path.resolve()
            resolved_relative = resolved.relative_to(root)
        except (OSError, ValueError):
            continue
        if (
            any(part in excluded_names for part in lexical_relative.parts)
            or any(part in excluded_names for part in resolved_relative.parts)
            or not resolved.is_file()
        ):
            continue
        sources.add(resolved)
    return sorted(
        sources,
        key=lambda path: path.relative_to(root).as_posix().casefold(),
    )


def observe_source_identity(
    root: str | Path,
    excluded: Iterable[str] = (),
    *,
    budget: AnalysisBudget | None = None,
) -> SourceIdentity:
    """Observe source identity without building or mutating a graph."""

    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"Analysis root is not a directory: {root_path}")
    active_budget = budget or AnalysisBudget()
    digest = sha256()
    latest_mtime_ns = 0
    source_paths = discover_sources(root_path, excluded, budget=active_budget)
    for path in source_paths:
        active_budget.consume("source_discovery")
        relative = path.relative_to(root_path).as_posix()
        data = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
        latest_mtime_ns = max(latest_mtime_ns, path.stat().st_mtime_ns)
    return SourceIdentity(digest.hexdigest(), len(source_paths), latest_mtime_ns)


def analyze_repository(
    root: str | Path,
    include_roots: Iterable[str | Path] = (),
    excluded: Iterable[str] = (),
    *,
    max_work: int | None = None,
    budget: AnalysisBudget | None = None,
) -> CodeGraph:
    if budget is not None and max_work is not None:
        raise ValueError("Specify either max_work or budget, not both")
    active_budget = budget or AnalysisBudget(max_work)
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"Analysis root is not a directory: {root_path}")
    include_paths: list[Path] = []
    for path in include_roots:
        active_budget.consume("source_discovery")
        include_paths.append(Path(path).resolve())
    source_paths = discover_sources(root_path, excluded, budget=active_budget)
    digest = sha256()
    units: list[ParsedUnit] = []
    decode_diagnostics: list[Diagnostic] = []
    for path in source_paths:
        active_budget.consume("source_discovery")
        relative = path.relative_to(root_path).as_posix()
        data = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")
            decode_diagnostics.append(Diagnostic(
                DECODE_RECOVERY, "warning", "Invalid UTF-8 bytes replaced during decoding",
                SourceLocation(relative, 1, 1),
            ))
        units.append(
            ParsedUnit(
                path.resolve(),
                relative,
                parse_source(text, relative, budget=active_budget),
            )
        )
    graph, _ = build_graph(
        units,
        root_path,
        include_paths,
        digest.hexdigest(),
        budget=active_budget,
    )
    for diagnostic in decode_diagnostics:
        graph.add_diagnostic(diagnostic)
    enrich_runtime(graph, budget=active_budget)
    graph.metadata.update({
        "node_count": len(graph.nodes), "edge_count": len(graph.edges),
        "diagnostic_count": len(graph.diagnostics),
    })
    return graph
