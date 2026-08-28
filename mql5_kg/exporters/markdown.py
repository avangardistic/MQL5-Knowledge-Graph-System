"""Human-readable Markdown report generation from a canonical graph.

The report is a projection of the canonical graph: it never reinterprets
semantics and never invents evidence. JSON export is available through
``CodeGraph.to_json``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..graph import CodeGraph, GraphNode

_KIND_LABELS = {
    "event_handler": "event handlers",
    "function": "functions",
    "method": "methods",
    "constructor": "constructors",
    "destructor": "destructors",
    "class": "classes",
    "struct": "structs",
    "enum": "enums",
    "input_variable": "input variables",
    "macro": "macros",
    "property": "properties",
    "imported_symbol": "imported symbols",
    "external_function": "external functions",
    "runtime": "runtime entities",
    "file": "files",
}


def export_markdown(
    graph: CodeGraph,
    path: str | Path,
    *,
    max_nodes_per_kind: int = 200,
) -> None:
    lines: list[str] = []
    lines.append("# MQL5 Knowledge Graph Report")
    lines.append("")
    lines.append("> Generated from the canonical graph. Evidence and confidence are preserved;")
    lines.append("> this report never reinterprets graph semantics.")
    lines.append("")

    metadata = graph.metadata
    lines.append("## Project")
    lines.append("")
    lines.append(f"- Schema version: `{graph.schema_version}`")
    lines.append(f"- Files indexed: {metadata.get('file_count', '?')}")
    lines.append(f"- Nodes: {len(graph.nodes)}")
    lines.append(f"- Edges: {len(graph.edges)}")
    lines.append(f"- Diagnostics: {len(graph.diagnostics)}")
    lines.append(f"- Source fingerprint: `{metadata.get('source_fingerprint', '?')}`")
    lines.append(f"- Tool version: `{metadata.get('tool_version', '?')}`")
    lines.append("")

    counts: dict[str, int] = {}
    by_file: dict[str, list[GraphNode]] = {}
    for node in graph.nodes.values():
        counts[node.kind] = counts.get(node.kind, 0) + 1
        if node.location is not None:
            by_file.setdefault(node.location.file, []).append(node)

    lines.append("## Nodes by kind")
    lines.append("")
    for kind, count in sorted(counts.items(), key=lambda item: -item[1]):
        lines.append(f"- {_KIND_LABELS.get(kind, kind)}: {count}")
    lines.append("")

    lines.append("## Files")
    lines.append("")
    for file_path in sorted(by_file):
        nodes = sorted(by_file[file_path], key=lambda n: n.location.line if n.location else 0)
        lines.append(f"### `{file_path}`")
        lines.append("")
        lines.append(f"{len(nodes)} symbols")
        lines.append("")
        for node in nodes[:max_nodes_per_kind]:
            loc = f"line {node.location.line}" if node.location else "unknown location"
            lines.append(f"- `{node.name}` ({node.kind}) — {loc}")
        if len(nodes) > max_nodes_per_kind:
            lines.append(f"- … and {len(nodes) - max_nodes_per_kind} more")
        lines.append("")

    lines.append("## Relationship summary")
    lines.append("")
    rel_counts: dict[str, int] = {}
    origins: dict[str, int] = {}
    for edge in graph.edges.values():
        rel_counts[edge.relationship] = rel_counts.get(edge.relationship, 0) + 1
        origins[edge.origin] = origins.get(edge.origin, 0) + 1
    lines.append("### By relationship")
    lines.append("")
    for relationship, count in sorted(rel_counts.items(), key=lambda item: -item[1]):
        lines.append(f"- {relationship}: {count}")
    lines.append("")
    lines.append("### By origin")
    lines.append("")
    for origin, count in sorted(origins.items(), key=lambda item: -item[1]):
        lines.append(f"- {origin}: {count}")
    lines.append("")

    lines.append("## Diagnostics")
    lines.append("")
    if graph.diagnostics:
        for diagnostic in graph.diagnostics[:200]:
            location = ""
            if diagnostic.location is not None:
                location = f" at {diagnostic.location.file}:{diagnostic.location.line}"
            lines.append(f"- `{diagnostic.code}` [{diagnostic.severity}]{location}: {diagnostic.message}")
        if len(graph.diagnostics) > 200:
            lines.append(f"- … and {len(graph.diagnostics) - 200} more")
    else:
        lines.append("None.")
    lines.append("")

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
