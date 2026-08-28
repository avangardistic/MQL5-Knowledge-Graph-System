"""The ``mql5kg`` command-line interface.

A thin adapter over the Intelligence Kernel: every query loads a canonical
graph, builds a kernel, and projects the contract result. Human output is
compact by default; ``--json`` emits the full machine-readable contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from ..analysis_budget import AnalysisBudget, AnalysisBudgetExceeded
from ..exporters import export_graphml, export_markdown
from ..graph import CodeGraph
from ..incremental import FileCache, incremental_analysis, persist_incremental
from ..indexer import analyze_repository
from ..intelligence import (
    IntelligenceError,
    IntelligenceKernel,
)
from ..intelligence.models import GraphIdentity, IntelligenceRequest
from ..snapshots import GraphSnapshot, GraphValidationError
from ..version import __version__


def _emit(value: Any, as_json: bool, human: str | None = None) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    elif human is not None:
        print(human)
    else:
        print(value)


def _emit_error(value: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(
            json.dumps({"error": value}, ensure_ascii=False, indent=2, sort_keys=True),
            file=sys.stderr,
        )
    else:
        print(f"error: {value['message']}", file=sys.stderr)


def _load_kernel(graph_path: str, revision: int = 1) -> IntelligenceKernel:
    graph = CodeGraph.load(graph_path)
    return IntelligenceKernel(graph, snapshot_revision=revision)


def _selector(value: str) -> dict[str, str | None]:
    return {"value": value, "kind": None}


def _print_intelligence(result: Any, as_json: bool, human: str) -> None:
    _emit(result.to_dict(), as_json, human)


def _human_target(resolution) -> str:
    if resolution.status == "no_match":
        return "no match"
    if resolution.status == "ambiguous":
        names = ", ".join(sorted(resolution.selector.value for _ in resolution.candidates))
        return f"ambiguous ({len(resolution.candidates)} candidates)"
    return "matched"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mql5kg",
        description="MQL5 Knowledge Graph System — index, query, and export MQL5 codegraphs",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command", required=True)

    index = subcommands.add_parser("index", help="Index an MQL5 source tree into a canonical graph")
    index.add_argument("root")
    index.add_argument("--output", "-o", default="graph.json")
    index.add_argument("--include-root", action="append", default=[])
    index.add_argument("--exclude", action="append", default=[])
    index.add_argument("--max-work", type=int)
    index.add_argument("--incremental", action="store_true",
                       help="Reuse parsed unchanged files across runs (persists a content-hash cache)")
    index.add_argument("--cache", default=None,
                       help="Path for the incremental ParseResult cache (default: <output>.cache.json)")
    index.add_argument("--json", action="store_true")

    status = subcommands.add_parser("status", help="Show saved graph metadata")
    status.add_argument("graph")
    status.add_argument("--json", action="store_true")

    search = subcommands.add_parser("search", help="Search symbols in a graph")
    search.add_argument("graph")
    search.add_argument("query")
    search.add_argument("--kind")
    search.add_argument("--max-items", type=int, default=30)
    search.add_argument("--json", action="store_true")

    symbol = subcommands.add_parser("symbol", help="Resolve a symbol (definition)")
    symbol.add_argument("graph")
    symbol.add_argument("name")
    symbol.add_argument("--json", action="store_true")

    callers = subcommands.add_parser("callers", help="Who calls this symbol?")
    callers.add_argument("graph")
    callers.add_argument("name")
    callers.add_argument("--max-depth", type=int, default=1)
    callers.add_argument("--max-items", type=int, default=200)
    callers.add_argument("--json", action="store_true")

    callees = subcommands.add_parser("callees", help="What does this symbol call?")
    callees.add_argument("graph")
    callees.add_argument("name")
    callees.add_argument("--max-depth", type=int, default=1)
    callees.add_argument("--max-items", type=int, default=200)
    callees.add_argument("--json", action="store_true")

    references = subcommands.add_parser("references", help="All references to a symbol")
    references.add_argument("graph")
    references.add_argument("name")
    references.add_argument("--max-depth", type=int, default=1)
    references.add_argument("--max-items", type=int, default=200)
    references.add_argument("--json", action="store_true")

    impact = subcommands.add_parser("impact", help="Upstream impact of changing a symbol")
    impact.add_argument("graph")
    impact.add_argument("name")
    impact.add_argument("--max-depth", type=int, default=3)
    impact.add_argument("--max-items", type=int, default=500)
    impact.add_argument("--json", action="store_true")

    trace = subcommands.add_parser("trace", help="Directed paths between two symbols")
    trace.add_argument("graph")
    trace.add_argument("source")
    trace.add_argument("target")
    trace.add_argument("--max-depth", type=int, default=5)
    trace.add_argument("--max-paths", type=int, default=3)
    trace.add_argument("--json", action="store_true")

    context = subcommands.add_parser("context", help="Compact AI-oriented context package")
    context.add_argument("graph")
    context.add_argument("name")
    context.add_argument("--budget", "--context-units", dest="context_units", type=int, default=100)
    context.add_argument("--max-depth", type=int, default=2)
    context.add_argument("--direction", choices=["incoming", "outgoing", "both"], default="both")
    context.add_argument("--json", action="store_true")

    diagnostics = subcommands.add_parser("diagnostics", help="Graph diagnostics")
    diagnostics.add_argument("graph")
    diagnostics.add_argument("--max-items", type=int, default=250)
    diagnostics.add_argument("--json", action="store_true")

    export = subcommands.add_parser("export", help="Export a graph (graphml | markdown | json)")
    export.add_argument("graph")
    export.add_argument("--format", choices=["graphml", "markdown", "json"], required=True)
    export.add_argument("--output", "-o", required=True)
    export.add_argument("--json", action="store_true")

    serve = subcommands.add_parser("serve", help="Start the HTTP API adapter")
    serve.add_argument("--graph", required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    return parser


def _resolve(graph_path: str, name: str, kind: str | None = None) -> IntelligenceKernel:
    return _load_kernel(graph_path)


def _summary_lines(result: Any) -> str:
    """Compact human summary of an intelligence result."""

    lines: list[str] = []
    for resolution in result.resolution:
        if resolution.status == "no_match":
            lines.append(f"no match for {resolution.selector.value!r}")
        elif resolution.status == "ambiguous":
            lines.append(
                f"ambiguous: {len(resolution.candidates)} candidates for "
                f"{resolution.selector.value!r}"
            )
        else:
            lines.append(f"matched {resolution.selector.value!r}")
    for node in result.nodes:
        location = ""
        if node.location is not None:
            location = f" at {node.location.file}:{node.location.line}"
        lines.append(f"{node.kind}: {node.qualified_name}{location}")
    result_nodes = {node.id: node.qualified_name for node in result.nodes}
    for relationship in result.relationships:
        lines.append(
            f"{relationship.relationship} [{relationship.evidence.origin}, "
            f"conf {relationship.evidence.confidence}]"
        )
    for path in result.paths:
        names = " -> ".join(
            result_nodes.get(node_id, node_id)
            for node_id in path.node_ids
        )
        lines.append(f"path {path.rank}: {names}")
    if result.context_package is not None:
        package = result.context_package
        lines.append(
            f"context budget {package.budget_used}/{package.budget_limit}"
        )
        for omission in package.omissions:
            lines.append(f"omitted {omission.category}: {omission.count}")
    completion = result.completion
    if completion.truncated:
        lines.append(
            f"truncated: {completion.reason} ({completion.omitted_counts})"
        )
    return "\n".join(lines)


def run(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)

    if args.command == "index":
        try:
            AnalysisBudget(args.max_work)
        except ValueError as error:
            _emit_error(
                {"code": "invalid_parameter", "message": str(error), "field": "max_work"},
                args.json,
            )
            return 1
        try:
            if args.incremental:
                output_path = Path(args.output).resolve()
                cache_abs = Path(args.cache).resolve() if args.cache else output_path.with_name(
                    output_path.stem + ".cache.json"
                )
                result, cache = incremental_analysis(
                    args.root,
                    args.include_root,
                    args.exclude,
                    max_work=args.max_work,
                    cache_path=cache_abs,
                )
                graph = result.graph
                snapshot = GraphSnapshot.publish(graph, revision=1)
                persist_incremental(result, cache, graph_path=output_path, cache_path=cache_abs)
                output = str(output_path)
                summary = {
                    "output": output,
                    "mode": result.mode,
                    "reused_files": result.reused_files,
                    "changed_files": list(result.changed_files),
                    "removed_files": list(result.removed_files),
                    "files": graph.metadata["file_count"],
                    "nodes": len(graph.nodes),
                    "edges": len(graph.edges),
                    "diagnostics": len(graph.diagnostics),
                    "source_fingerprint": graph.metadata["source_fingerprint"],
                    "graph_fingerprint": snapshot.fingerprint,
                }
            else:
                graph = analyze_repository(
                    args.root,
                    args.include_root,
                    args.exclude,
                    max_work=args.max_work,
                )
                snapshot = GraphSnapshot.publish(graph, revision=1)
                output = Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                graph.save(output)
                summary = {
                    "output": str(output.resolve()),
                    "files": graph.metadata["file_count"],
                    "nodes": len(graph.nodes),
                    "edges": len(graph.edges),
                    "diagnostics": len(graph.diagnostics),
                    "source_fingerprint": graph.metadata["source_fingerprint"],
                    "graph_fingerprint": snapshot.fingerprint,
                }
        except AnalysisBudgetExceeded as error:
            _emit_error(error.to_dict(), args.json)
            return 1
        except GraphValidationError as error:
            _emit_error(error.to_dict(), args.json)
            return 1
        human = f"Indexed {summary['files']} files: {summary['nodes']} nodes, " \
            f"{summary['edges']} edges, {summary['diagnostics']} diagnostics -> {summary['output']}"
        if summary.get("mode") is not None:
            human += f" (mode: {summary['mode']}, reused: {summary['reused_files']})"
        _emit(
            summary,
            args.json,
            human,
        )
        return 0

    try:
        graph = CodeGraph.load(args.graph)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        _emit_error(
            {"code": "graph_load_failed", "message": f"Could not load graph: {error}"},
            args.json,
        )
        return 1

    if args.command == "status":
        severities: dict[str, int] = {}
        for diagnostic in graph.diagnostics:
            severities[diagnostic.severity] = severities.get(diagnostic.severity, 0) + 1
        result = {
            "schema_version": graph.schema_version,
            "files": graph.metadata.get("file_count", 0),
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "diagnostics": severities,
            "source_fingerprint": graph.metadata.get("source_fingerprint"),
        }
        _emit(
            result,
            args.json,
            f"Schema {result['schema_version']}: {result['files']} files, "
            f"{result['nodes']} nodes, {result['edges']} edges",
        )
        return 0

    if args.command == "export":
        if args.format == "graphml":
            export_graphml(graph, args.output)
        elif args.format == "markdown":
            export_markdown(graph, args.output)
        else:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(graph.to_json(), encoding="utf-8")
        value = {
            "format": args.format,
            "output": str(Path(args.output).resolve()),
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
        }
        _emit(value, args.json, f"Exported {args.format} -> {args.output}")
        return 0

    if args.command == "serve":
        from .http import serve_http

        serve_http(graph, host=args.host, port=args.port)
        return 0

    # Query commands over the kernel
    kernel = IntelligenceKernel(graph, snapshot_revision=1)
    request: dict[str, Any] = {
        "contract_version": "1.0.0",
        "direction": "both",
        "relationship_types": [],
        "node_kinds": [],
        "bounds": {
            "max_depth": 1,
            "max_items": 30,
            "max_paths": 3,
            "max_expansions": 10_000,
            "context_units": 100,
        },
        "expected_source_fingerprint": None,
        "client_request_id": None,
    }
    try:
        if args.command == "search":
            request.update(
                {
                    "operation": "query",
                    "targets": [{"value": args.query, "kind": args.kind}],
                    "bounds": {"max_items": args.max_items, "max_depth": 1,
                               "max_paths": 3, "max_expansions": 10_000, "context_units": 100},
                }
            )
            result = kernel.execute(request)
            human = "\n".join(
                f"{node.kind}: {node.qualified_name}"
                + (f" at {node.location.file}:{node.location.line}" if node.location else "")
                for node in result.nodes
            ) or "No matches"
        elif args.command == "symbol":
            request.update({"operation": "query", "targets": [_selector(args.name)]})
            result = kernel.execute(request)
            human = _summary_lines(result)
        elif args.command == "callers":
            request.update(
                {
                    "operation": "context",
                    "targets": [_selector(args.name)],
                    "direction": "incoming",
                    "relationship_types": ["calls"],
                    "bounds": {"max_depth": args.max_depth, "max_items": args.max_items,
                               "max_paths": 3, "max_expansions": 10_000, "context_units": 100},
                }
            )
            result = kernel.execute(request)
            human = "\n".join(
                f"{node.qualified_name}" for node in result.nodes
                if node.id not in {c.node_id for c in result.resolution[0].candidates}
            ) or "No callers found"
        elif args.command == "callees":
            request.update(
                {
                    "operation": "context",
                    "targets": [_selector(args.name)],
                    "direction": "outgoing",
                    "relationship_types": ["calls"],
                    "bounds": {"max_depth": args.max_depth, "max_items": args.max_items,
                               "max_paths": 3, "max_expansions": 10_000, "context_units": 100},
                }
            )
            result = kernel.execute(request)
            human = "\n".join(
                f"{node.qualified_name}" for node in result.nodes
                if node.id not in {c.node_id for c in result.resolution[0].candidates}
            ) or "No callees found"
        elif args.command == "references":
            request.update(
                {
                    "operation": "context",
                    "targets": [_selector(args.name)],
                    "direction": "both",
                    "bounds": {"max_depth": args.max_depth, "max_items": args.max_items,
                               "max_paths": 3, "max_expansions": 10_000, "context_units": 100},
                }
            )
            result = kernel.execute(request)
            human = _summary_lines(result)
        elif args.command == "impact":
            request.update(
                {
                    "operation": "impact",
                    "targets": [_selector(args.name)],
                    "direction": "incoming",
                    "bounds": {"max_depth": args.max_depth, "max_items": args.max_items,
                               "max_paths": 3, "max_expansions": 10_000, "context_units": 100},
                }
            )
            result = kernel.execute(request)
            human = "\n".join(
                f"{node.kind}: {node.qualified_name}"
                + (f" at {node.location.file}:{node.location.line}" if node.location else "")
                for node in result.nodes
            ) or "No upstream impact found"
        elif args.command == "trace":
            request.update(
                {
                    "operation": "path",
                    "targets": [_selector(args.source), _selector(args.target)],
                    "direction": "outgoing",
                    "bounds": {"max_depth": args.max_depth, "max_items": 30,
                               "max_paths": args.max_paths, "max_expansions": 10_000,
                               "context_units": 100},
                }
            )
            result = kernel.execute(request)
            human = _summary_lines(result)
        elif args.command == "context":
            request.update(
                {
                    "operation": "context_package",
                    "targets": [_selector(args.name)],
                    "direction": args.direction,
                    "bounds": {"max_depth": args.max_depth, "max_items": 200,
                               "max_paths": 3, "max_expansions": 10_000,
                               "context_units": args.context_units},
                }
            )
            result = kernel.execute(request)
            human = _summary_lines(result)
        elif args.command == "diagnostics":
            request.update(
                {
                    "operation": "diagnostics",
                    "targets": [],
                    "bounds": {"max_depth": 1, "max_items": args.max_items,
                               "max_paths": 3, "max_expansions": 10_000, "context_units": 100},
                }
            )
            result = kernel.execute(request)
            human = "\n".join(
                f"[{d.severity}] {d.code}: {d.message}"
                + (f" ({d.evidence.location.file}:{d.evidence.location.line})" if d.evidence.location else "")
                for d in result.diagnostics
            ) or "No diagnostics"
        else:
            raise ValueError(f"unknown command {args.command!r}")
    except (ValueError, IntelligenceError) as error:
        normalized = (
            error
            if isinstance(error, IntelligenceError)
            else IntelligenceError.invalid_request(str(error))
        )
        _emit_error(normalized.to_dict(), args.json)
        return 1
    _emit(result.to_dict(), args.json, human)
    return 0


def main() -> int:
    try:
        return run()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
