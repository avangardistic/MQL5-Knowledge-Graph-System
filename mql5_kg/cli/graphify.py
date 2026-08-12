#!/usr/bin/env python3
"""
MQL5 Knowledge Graph CLI - Build, query, and serve knowledge graphs for MQL5 codebases.

Usage:
    python -m mql5_kg.cli.graphify build <path> [--report] [-o <output>]
    python -m mql5_kg.cli.graphify query <command> [args...]
    python -m mql5_kg.cli.graphify serve [--graph <path>]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List


def find_mql5_files(root_path: str) -> List[Path]:
    """Find all MQL5 files in a directory."""
    root = Path(root_path)
    if not root.exists():
        print(f"Error: Path does not exist: {root_path}", file=sys.stderr)
        return []
    
    extensions = {'.mq5', '.mqh', '.mqproj'}
    files = []
    
    if root.is_file():
        if root.suffix.lower() in extensions:
            files.append(root)
    else:
        for ext in extensions:
            files.extend(root.rglob(f'*{ext}'))
    
    return sorted(files)


def build_graph(source_path: str, output_dir: str = '.', generate_report: bool = False) -> Dict[str, Any]:
    """Build a knowledge graph from MQL5 files."""
    from ..parser import MQL5Parser
    from ..storage import GraphStorage
    
    # Find MQL5 files
    mql5_files = find_mql5_files(source_path)
    if not mql5_files:
        print(f"No MQL5 files found in: {source_path}", file=sys.stderr)
        return {}
    
    print(f"Found {len(mql5_files)} MQL5 file(s)")
    
    # Parse files
    parser = MQL5Parser()
    for i, file_path in enumerate(mql5_files, 1):
        result = parser.parse_file(str(file_path))
        if 'error' in result:
            print(f"  [{i}/{len(mql5_files)}] Error parsing {file_path}: {result['error']}", file=sys.stderr)
        else:
            print(f"  [{i}/{len(mql5_files)}] Parsed {file_path.name}: {result['symbols_count']} symbols")
    
    # Get graph
    graph = parser.get_graph()
    
    # Save graph
    storage = GraphStorage(output_dir)
    graph_path = storage.save_graph(graph)
    print(f"\nGraph saved to: {graph_path}")
    
    # Generate report if requested
    if generate_report:
        report_path = storage.generate_report(graph)
        print(f"Report saved to: {report_path}")
    
    # Print statistics
    stats = graph.get('statistics', {})
    print(f"\nStatistics:")
    print(f"  Total symbols: {stats.get('total_symbols', 0)}")
    print(f"  Total edges: {stats.get('total_edges', 0)}")
    print(f"  Total files: {stats.get('total_files', 0)}")
    
    by_type = stats.get('by_type', {})
    if by_type:
        print(f"  By type:")
        for symbol_type, count in sorted(by_type.items()):
            print(f"    - {symbol_type}: {count}")
    
    return graph


def query_graph(command: str, args: List[str], graph_path: str = 'graph.json') -> None:
    """Query the knowledge graph."""
    from ..mcp_server import MCPServer
    
    # Load graph
    if not Path(graph_path).exists():
        print(f"Error: Graph file not found: {graph_path}", file=sys.stderr)
        print("Run 'build' first to create the graph.", file=sys.stderr)
        return
    
    server = MCPServer(graph_path)
    
    if command == 'search':
        query = ' '.join(args) if args else ''
        if not query:
            print("Usage: query search <query>", file=sys.stderr)
            return
        result = server.search_symbols(query)
    
    elif command == 'symbol':
        symbol_name = args[0] if args else ''
        if not symbol_name:
            print("Usage: query symbol <name>", file=sys.stderr)
            return
        result = server.get_symbol_context(symbol_name)
    
    elif command == 'impact':
        symbol_name = args[0] if args else ''
        if not symbol_name:
            print("Usage: query impact <symbol>", file=sys.stderr)
            return
        result = server.impact_analysis(symbol_name)
    
    elif command == 'trace':
        if len(args) < 2:
            print("Usage: query trace <start> <end>", file=sys.stderr)
            return
        result = server.trace_execution_flow(args[0], args[1])
    
    elif command == 'file':
        file_path = args[0] if args else ''
        if not file_path:
            print("Usage: query file <path>", file=sys.stderr)
            return
        result = server.get_file_summary(file_path)
    
    elif command == 'includes':
        file_path = args[0] if args else ''
        if not file_path:
            print("Usage: query includes <path>", file=sys.stderr)
            return
        result = server.resolve_includes(file_path)
    
    else:
        print(f"Unknown query command: {command}", file=sys.stderr)
        print("Available commands: search, symbol, impact, trace, file, includes", file=sys.stderr)
        return
    
    # Output result
    print(json.dumps(result, indent=2))


def serve_graph(graph_path: str = 'graph.json') -> None:
    """Start the MCP server."""
    import asyncio
    from ..mcp_server import MCPServer
    
    server = MCPServer(graph_path)
    
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\nServer stopped.")


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog='graphify',
        description='MQL5 Knowledge Graph CLI - Build, query, and serve knowledge graphs'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Build command
    build_parser = subparsers.add_parser('build', help='Build knowledge graph from MQL5 files')
    build_parser.add_argument('path', help='Path to MQL5 files (directory or single file)')
    build_parser.add_argument('-o', '--output', default='.', help='Output directory (default: current)')
    build_parser.add_argument('--report', action='store_true', help='Generate Markdown report')
    
    # Query command
    query_parser = subparsers.add_parser('query', help='Query the knowledge graph')
    query_parser.add_argument('subcommand', choices=['search', 'symbol', 'impact', 'trace', 'file', 'includes'],
                             help='Query type')
    query_parser.add_argument('args', nargs='*', help='Query arguments')
    query_parser.add_argument('--graph', default='graph.json', help='Path to graph.json')
    
    # Serve command
    serve_parser = subparsers.add_parser('serve', help='Start MCP server')
    serve_parser.add_argument('--graph', default='graph.json', help='Path to graph.json')
    
    args = parser.parse_args()
    
    if args.command == 'build':
        build_graph(args.path, args.output, args.report)
    
    elif args.command == 'query':
        query_graph(args.subcommand, args.args, args.graph)
    
    elif args.command == 'serve':
        serve_graph(args.graph)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
