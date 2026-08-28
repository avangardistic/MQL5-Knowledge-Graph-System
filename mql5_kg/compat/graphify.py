"""Legacy ``graphify`` CLI compatibility adapter.

Maps the historical command surface onto the new core:

- ``build <path> [-o output] [--report]``  → new indexer + canonical graph.json
- ``query search|symbol|impact|trace|file|includes ... --graph graph.json``
  → new kernel with the historical result shapes
- ``serve --graph graph.json``             → new MCP server

Deprecated: prefer the ``mql5kg`` CLI. This module exists so existing scripts
keep working; it is a thin projector over the new core (never a second
implementation of graph semantics).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from ..graph import CodeGraph
from ..indexer import analyze_repository
from ..intelligence import IntelligenceKernel
from ..version import __version__


def _load_kernel(graph_path: str) -> IntelligenceKernel:
    graph = CodeGraph.load(graph_path)
    return IntelligenceKernel(graph, snapshot_revision=1)


def find_mql5_files(root_path: str) -> List[Path]:
    """Locate MQL5 files under a directory or single file path."""

    root = Path(root_path)
    if not root.exists():
        return []
    extensions = {".mq5", ".mqh", ".mqproj"}
    if root.is_file():
        return [root] if root.suffix.lower() in extensions else []
    files: List[Path] = []
    for ext in extensions:
        files.extend(root.rglob(f"*{ext}"))
    return sorted(files)


def build_graph(
    source_path: str,
    output_dir: str = ".",
    generate_report: bool = False,
) -> Dict[str, Any]:
    """Build a canonical graph and emit the historical summary dict."""

    root = Path(source_path).resolve()
    graph = analyze_repository(root)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    graph_path = output / "graph.json"
    graph.save(graph_path)

    if generate_report:
        from ..exporters import export_markdown

        export_markdown(graph, output / "GRAPH_REPORT.md")

    by_type: Dict[str, int] = {}
    for node in graph.nodes.values():
        by_type[node.kind] = by_type.get(node.kind, 0) + 1
    return {
        "statistics": {
            "total_symbols": len(graph.nodes),
            "total_edges": len(graph.edges),
            "total_files": graph.metadata.get("file_count", 0),
            "by_type": by_type,
        },
        "graph_path": str(graph_path),
    }


def _legacy_definition(node: Any) -> Dict[str, Any]:
    return_type = node.attributes.get("return_type") or "void"
    parameter_count = node.attributes.get("parameter_count")
    signature = str(node.attributes.get("signature", ""))
    parameters = ""
    if "(" in signature and signature.rstrip().endswith(")"):
        parameters = signature[signature.find("(") + 1 : signature.rfind(")")]
    return {
        "name": node.name,
        "type": node.kind,
        "file": node.location.file if node.location else "",
        "line_start": node.location.line if node.location else None,
        "return_type": return_type,
        "parameters": parameters if parameters else parameter_count,
    }


def _legacy_symbol_context(kernel: IntelligenceKernel, symbol_name: str) -> Dict[str, Any]:
    result = kernel.execute({
        "operation": "context",
        "targets": [{"value": symbol_name, "kind": None}],
        "direction": "both",
        "bounds": {"max_depth": 1, "max_items": 900},
    })
    resolution = result.resolution[0]
    if resolution.status == "no_match":
        fuzzy = kernel.execute({
            "operation": "query",
            "targets": [{"value": symbol_name, "kind": None}],
            "direction": "both",
            "bounds": {"max_depth": 1, "max_items": 30},
        })
        if fuzzy.resolution[0].status == "no_match":
            return {"error": f"Symbol '{symbol_name}' not found"}
        result = kernel.execute({
            "operation": "context",
            "targets": [{"value": fuzzy.nodes[0].name, "kind": None}],
            "direction": "both",
            "bounds": {"max_depth": 1, "max_items": 900},
        })
        resolution = result.resolution[0]
    target_ids = {candidate.node_id for candidate in resolution.candidates}
    caller_ids = {
        relationship.source for relationship in result.relationships
        if relationship.relationship == "calls" and relationship.target in target_ids
    }
    callee_ids = {
        relationship.target for relationship in result.relationships
        if relationship.relationship == "calls" and relationship.source in target_ids
    }
    index = kernel.index
    definition = None
    for node in result.nodes:
        if node.id in target_ids:
            definition = _legacy_definition(node)
            break
    if definition is None and resolution.status == "matched":
        node = index.nodes[resolution.candidates[0].node_id]
        definition = _legacy_definition(node)
    return {
        "definition": definition or {"name": symbol_name, "type": "unknown"},
        "callers": sorted({index.nodes[node_id].name for node_id in caller_ids}),
        "callees": sorted({index.nodes[node_id].name for node_id in callee_ids}),
    }


def _legacy_impact(kernel: IntelligenceKernel, symbol_name: str) -> Dict[str, Any]:
    result = kernel.execute({
        "operation": "impact",
        "targets": [{"value": symbol_name, "kind": None}],
        "direction": "incoming",
        "bounds": {"max_depth": 3, "max_items": 2000},
    })
    resolution = result.resolution[0]
    if resolution.status == "no_match":
        return {"error": f"Symbol '{symbol_name}' not found"}
    index = kernel.index
    target_ids = {candidate.node_id for candidate in resolution.candidates}
    dependents: List[Dict[str, Any]] = []
    for relationship in result.relationships:
        if relationship.relationship != "calls":
            continue
        if relationship.target in target_ids and relationship.source not in target_ids:
            node = index.nodes[relationship.source]
            dependents.append({
                "symbol": node.qualified_name,
                "relationship": relationship.relationship,
            })
    target_node = index.nodes[resolution.candidates[0].node_id]
    return {
        "symbol": symbol_name,
        "type": target_node.kind,
        "file": target_node.location.file if target_node.location else "",
        "dependents_count": len(dependents),
        "dependents": dependents[:50],
    }


def _legacy_trace(kernel: IntelligenceKernel, start: str, end: str) -> Dict[str, Any]:
    result = kernel.execute({
        "operation": "path",
        "targets": [{"value": start, "kind": None}, {"value": end, "kind": None}],
        "direction": "outgoing",
        "bounds": {"max_depth": 5, "max_paths": 3, "max_expansions": 10_000},
    })
    if result.completion.reason == "no_match":
        return {"found": False, "message": f"No path found from '{start}' to '{end}'"}
    if not result.paths:
        return {"found": False, "message": f"No path found from '{start}' to '{end}'"}
    path = result.paths[0]
    index = kernel.index
    names = [
        index.nodes[node_id].name if node_id in index.nodes else node_id
        for node_id in path.node_ids
    ]
    return {"found": True, "path": names, "length": len(names)}


def _legacy_file_summary(kernel: IntelligenceKernel, file_path: str) -> Dict[str, Any]:
    result = kernel.execute({
        "operation": "context",
        "targets": [{"value": file_path, "kind": "file"}],
        "direction": "outgoing",
        "bounds": {"max_depth": 1, "max_items": 2000},
    })
    resolution = result.resolution[0]
    if resolution.status == "no_match":
        matches = kernel.execute({
            "operation": "query",
            "targets": [{"value": file_path, "kind": "file"}],
            "direction": "both",
            "bounds": {"max_items": 30},
        })
        file_nodes = [node for node in matches.nodes if node.kind == "file"]
        if not file_nodes:
            return {"error": f"File '{file_path}' not found"}
        file_node = file_nodes[0]
    else:
        file_node = kernel.index.nodes[resolution.candidates[0].node_id]
    index = kernel.index
    defined = sorted(
        (
            node
            for node in index.nodes.values()
            if node.location is not None
            and node.location.file == file_node.qualified_name
            and node.kind != "file"
        ),
        key=lambda node: node.location.line if node.location else 0,
    )
    return {
        "file": file_node.qualified_name,
        "name": file_node.name,
        "lines": None,
        "size": None,
        "symbols_count": len(defined),
        "symbols": [
            {
                "name": node.name,
                "type": node.kind,
                "line_start": node.location.line if node.location else None,
            }
            for node in defined
        ],
    }


def _legacy_includes(kernel: IntelligenceKernel, file_path: str) -> Dict[str, Any]:
    result = kernel.execute({
        "operation": "context",
        "targets": [{"value": file_path, "kind": "file"}],
        "direction": "outgoing",
        "relationship_types": ["includes"],
        "bounds": {"max_depth": 1, "max_items": 200},
    })
    resolution = result.resolution[0]
    if resolution.status == "no_match":
        return {"error": f"File '{file_path}' not found"}
    index = kernel.index
    target_ids = {candidate.node_id for candidate in resolution.candidates}
    resolved: List[Dict[str, Any]] = []
    for relationship in result.relationships:
        if relationship.relationship != "includes" or relationship.source not in target_ids:
            continue
        target_node = index.nodes.get(relationship.target)
        resolved.append({
            "file": index.nodes[relationship.source].qualified_name,
            "includes": target_node.qualified_name if target_node else relationship.target,
            "depth": 0,
        })
    return {"file": file_path, "resolved_includes": resolved, "circular_dependency": False}


def query_graph(command: str, args: List[str], graph_path: str = "graph.json") -> None:
    """Execute a legacy query against a canonical graph.json."""

    if not Path(graph_path).exists():
        print(f"Error: Graph file not found: {graph_path}", file=sys.stderr)
        print("Run 'build' first to create the graph.", file=sys.stderr)
        return
    kernel = _load_kernel(graph_path)

    if command == "search":
        query = " ".join(args) if args else ""
        if not query:
            print("Usage: query search <query>", file=sys.stderr)
            return
        result = kernel.execute({
            "operation": "query",
            "targets": [{"value": query, "kind": None}],
            "direction": "both",
            "bounds": {"max_items": 100},
        })
        results = [
            {
                "name": node.name,
                "type": node.kind,
                "file": node.location.file if node.location else "",
                "line_start": node.location.line if node.location else None,
            }
            for node in result.nodes
        ]
        payload = {"query": query, "results_count": len(results), "results": results}
    elif command == "symbol":
        symbol_name = args[0] if args else ""
        if not symbol_name:
            print("Usage: query symbol <name>", file=sys.stderr)
            return
        payload = _legacy_symbol_context(kernel, symbol_name)
    elif command == "impact":
        symbol_name = args[0] if args else ""
        if not symbol_name:
            print("Usage: query impact <symbol>", file=sys.stderr)
            return
        payload = _legacy_impact(kernel, symbol_name)
    elif command == "trace":
        if len(args) < 2:
            print("Usage: query trace <start> <end>", file=sys.stderr)
            return
        payload = _legacy_trace(kernel, args[0], args[1])
    elif command == "file":
        file_path = args[0] if args else ""
        if not file_path:
            print("Usage: query file <path>", file=sys.stderr)
            return
        payload = _legacy_file_summary(kernel, file_path)
    elif command == "includes":
        file_path = args[0] if args else ""
        if not file_path:
            print("Usage: query includes <path>", file=sys.stderr)
            return
        payload = _legacy_includes(kernel, file_path)
    else:
        print(f"Unknown query command: {command}", file=sys.stderr)
        print("Available commands: search, symbol, impact, trace, file, includes", file=sys.stderr)
        return
    print(json.dumps(payload, indent=2))


def serve_graph(graph_path: str = "graph.json") -> None:
    """Start the MCP server (legacy ``serve`` command)."""

    from ..adapters.mcp.server import main as mcp_main

    # The MCP server indexes projects at runtime; the legacy graph argument is
    # accepted for compatibility but the server session starts empty.
    sys.argv = ["mql5-kg-mcp"]
    mcp_main()


def main() -> None:
    """Legacy ``graphify`` entry point."""

    parser = argparse.ArgumentParser(
        prog="graphify",
        description="MQL5 Knowledge Graph CLI (legacy compatibility surface)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    build_parser = subparsers.add_parser("build", help="Build knowledge graph from MQL5 files")
    build_parser.add_argument("path", help="Path to MQL5 files (directory or single file)")
    build_parser.add_argument("-o", "--output", default=".", help="Output directory (default: current)")
    build_parser.add_argument("--report", action="store_true", help="Generate Markdown report")

    query_parser = subparsers.add_parser("query", help="Query the knowledge graph")
    query_parser.add_argument("subcommand", choices=["search", "symbol", "impact", "trace", "file", "includes"])
    query_parser.add_argument("args", nargs="*", help="Query arguments")
    query_parser.add_argument("--graph", default="graph.json", help="Path to graph.json")

    serve_parser = subparsers.add_parser("serve", help="Start MCP server")
    serve_parser.add_argument("--graph", default="graph.json", help="Path to graph.json")

    args = parser.parse_args()
    if args.command == "build":
        try:
            result = build_graph(args.path, args.output, args.report)
        except Exception as error:
            print(f"Error: {error}", file=sys.stderr)
            sys.exit(1)
        stats = result["statistics"]
        print(f"\nGraph saved to: {result['graph_path']}")
        if args.report:
            print(f"Report saved to: {Path(args.output) / 'GRAPH_REPORT.md'}")
        print("\nStatistics:")
        print(f"  Total symbols: {stats['total_symbols']}")
        print(f"  Total edges: {stats['total_edges']}")
        print(f"  Total files: {stats['total_files']}")
        by_type = stats["by_type"]
        if by_type:
            print("  By type:")
            for symbol_type, count in sorted(by_type.items()):
                print(f"    - {symbol_type}: {count}")
    elif args.command == "query":
        query_graph(args.subcommand, args.args, args.graph)
    elif args.command == "serve":
        serve_graph(args.graph)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
