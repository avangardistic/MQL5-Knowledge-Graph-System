"""AI token-efficiency benchmark for structural context.

Compares three ways to give an AI the context needed for one representative
task (understanding and safely modifying a symbol):

- Approach A: the entire repository source.
- Approach B: the source files that define the symbol.
- Approach C: a bounded context package from the graph, plus the source lines
  of the symbol's definition.

Token estimate: ``chars / 4`` (conservative, ASCII-oriented). Every measurement
is recorded; no savings are claimed without numbers.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..graph import CodeGraph
from ..indexer import analyze_repository
from ..intelligence import IntelligenceKernel

TOKEN_ESTIMATE_DIVISOR = 4.0


def _estimate_tokens(text: str) -> int:
    return int(len(text) / TOKEN_ESTIMATE_DIVISOR)


def _source_bytes(root: Path, extension: tuple[str, ...] = (".mq5", ".mqh")) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in extension:
            total += path.stat().st_size
    return total


def _definition_window(graph: CodeGraph, kernel: IntelligenceKernel, symbol: str) -> str:
    """Return a bounded source excerpt around the symbol's definition, if any."""

    result = kernel.execute({
        "operation": "query",
        "targets": [{"value": symbol, "kind": None}],
        "direction": "both",
    })
    if result.resolution[0].status == "no_match":
        return ""
    node = result.nodes[0]
    if node.location is None:
        return ""
    file_path = Path(graph.metadata["root"]) / node.location.file
    try:
        lines = file_path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return ""
    start = max(0, node.location.line - 5)
    end = min(len(lines), node.location.line + 15)
    return "\n".join(lines[start:end])


def benchmark_context(
    root: str | Path,
    symbol: str,
    *,
    context_units: int = 100,
    max_work: int | None = None,
) -> dict[str, Any]:
    """Measure token/byte/latency for the three context approaches."""

    root_path = Path(root).resolve()
    started = time.monotonic()
    graph = analyze_repository(str(root_path), max_work=max_work)
    index_seconds = time.monotonic() - started

    kernel = IntelligenceKernel(graph, snapshot_revision=1)
    started = time.monotonic()
    package_result = kernel.execute({
        "operation": "context_package",
        "targets": [{"value": symbol, "kind": None}],
        "direction": "both",
        "bounds": {"context_units": context_units, "max_depth": 2},
    })
    context_seconds = time.monotonic() - started

    package_json = package_result.to_json()
    graph_json = graph.to_json()
    definition = _definition_window(graph, kernel, symbol)

    whole_repo_chars = _source_bytes(root_path)
    defining_files_chars = 0
    for node in graph.nodes.values():
        if node.location is not None and node.name == symbol:
            file_path = root_path / node.location.file
            try:
                defining_files_chars += file_path.stat().st_size
            except OSError:
                pass

    return {
        "symbol": symbol,
        "context_units": context_units,
        "measurements": {
            "whole_repository": {
                "bytes": whole_repo_chars,
                "chars": whole_repo_chars,
                "estimated_tokens": _estimate_tokens("x" * whole_repo_chars),
            },
            "defining_files_only": {
                "bytes": defining_files_chars,
                "chars": defining_files_chars,
                "estimated_tokens": _estimate_tokens("x" * defining_files_chars),
            },
            "graph_context_package": {
                "bytes": len(package_json.encode("utf-8")),
                "chars": len(package_json),
                "estimated_tokens": _estimate_tokens(package_json),
            },
            "graph_plus_definition": {
                "bytes": len(package_json.encode("utf-8")) + len(definition.encode("utf-8")),
                "chars": len(package_json) + len(definition),
                "estimated_tokens": _estimate_tokens(package_json + definition),
            },
        },
        "latency_seconds": {
            "index": round(index_seconds, 3),
            "context_package": round(context_seconds, 3),
        },
        "graph_summary": {
            "files": graph.metadata["file_count"],
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "diagnostics": len(graph.diagnostics),
            "graph_json_bytes": len(graph_json.encode("utf-8")),
        },
        "methodology": {
            "token_estimate": "chars / 4",
            "context_package_budget": context_units,
            "definition_window": "5 lines before .. 15 lines after definition",
        },
    }


def run_benchmarks(
    root: str | Path,
    symbols: list[str],
    output: str | None = None,
    *,
    max_work: int | None = None,
) -> dict[str, Any]:
    """Run the token benchmark for each symbol and optionally write JSON."""

    results = {
        "symbols": [
            benchmark_context(root, symbol, max_work=max_work)
            for symbol in symbols
        ],
    }
    if output:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    return results


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="MQL5 KG token-efficiency benchmark")
    parser.add_argument("root", help="MQL5 project root")
    parser.add_argument("--symbol", action="append", default=["OnTick"],
                        help="Symbol to benchmark (repeatable)")
    parser.add_argument("--output", "-o", help="Optional JSON output path")
    parser.add_argument("--max-work", type=int, default=None,
                        help="Analysis work budget (default: standard budget)")
    args = parser.parse_args()
    payload = run_benchmarks(args.root, args.symbol, args.output, max_work=args.max_work)
    print(json.dumps(payload, indent=2, sort_keys=True))
    sys.exit(0)
