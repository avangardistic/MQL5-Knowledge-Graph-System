"""
MCP Server - Model Context Protocol server for AI assistant integration.
Provides tools for querying the MQL5 knowledge graph.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    # Fallback stubs for when mcp is not installed
    class Server:
        def __init__(self, name: str):
            self.name = name
            self._tools = []
        
        def list_tools(self):
            return self._tools
        
        def call_tool(self, name: str, arguments: dict):
            raise NotImplementedError("MCP not available - install with: pip install mcp")
    
    def stdio_server():
        raise ImportError("MCP not available - install with: pip install mcp")
    
    class TextContent:
        def __init__(self, type: str = "text", text: str = ""):
            self.type = type
            self.text = text
    
    class Tool:
        def __init__(self, name: str, description: str, inputSchema: dict):
            self.name = name
            self.description = description
            self.inputSchema = inputSchema


class MCPServer:
    """MCP Server for MQL5 Knowledge Graph queries."""
    
    def __init__(self, graph_path: str = 'graph.json'):
        self.graph_path = Path(graph_path)
        self.graph: Dict[str, Any] = {}
        self._load_graph()
        
        if MCP_AVAILABLE:
            self.server = Server("mql5-knowledge-graph")
            self._register_tools()
        else:
            self.server = None
    
    def _load_graph(self):
        """Load the knowledge graph from file."""
        if self.graph_path.exists():
            with open(self.graph_path, 'r', encoding='utf-8') as f:
                self.graph = json.load(f)
        else:
            print(f"Warning: Graph file not found at {self.graph_path}", file=sys.stderr)
    
    def _register_tools(self):
        """Register MCP tools."""
        if not MCP_AVAILABLE or not self.server:
            return
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            return [
                Tool(
                    name="get_symbol_context",
                    description="Returns definition, parameters, location, callers, and callees for a symbol",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol_name": {"type": "string", "description": "Name of the symbol to look up"}
                        },
                        "required": ["symbol_name"]
                    }
                ),
                Tool(
                    name="impact_analysis",
                    description="Shows what code might break if a symbol is modified",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol_name": {"type": "string", "description": "Name of the symbol to analyze"}
                        },
                        "required": ["symbol_name"]
                    }
                ),
                Tool(
                    name="trace_execution_flow",
                    description="Finds shortest call path between two symbols",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "start": {"type": "string", "description": "Starting symbol"},
                            "end": {"type": "string", "description": "Ending symbol"}
                        },
                        "required": ["start", "end"]
                    }
                ),
                Tool(
                    name="get_file_summary",
                    description="Lists symbols in a file without reading full content",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "Path to the file"}
                        },
                        "required": ["file_path"]
                    }
                ),
                Tool(
                    name="search_symbols",
                    description="Semantic search across the knowledge graph",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="resolve_includes",
                    description="Recursively resolves #include statements for a file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "Path to the file"}
                        },
                        "required": ["file_path"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> List[TextContent]:
            result = await self._handle_tool(name, arguments)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    async def _handle_tool(self, name: str, arguments: dict) -> Dict[str, Any]:
        """Handle tool calls."""
        if name == "get_symbol_context":
            return self.get_symbol_context(arguments.get("symbol_name", ""))
        elif name == "impact_analysis":
            return self.impact_analysis(arguments.get("symbol_name", ""))
        elif name == "trace_execution_flow":
            return self.trace_execution_flow(
                arguments.get("start", ""),
                arguments.get("end", "")
            )
        elif name == "get_file_summary":
            return self.get_file_summary(arguments.get("file_path", ""))
        elif name == "search_symbols":
            return self.search_symbols(arguments.get("query", ""))
        elif name == "resolve_includes":
            return self.resolve_includes(arguments.get("file_path", ""))
        else:
            return {"error": f"Unknown tool: {name}"}
    
    def get_symbol_context(self, symbol_name: str) -> Dict[str, Any]:
        """Get context for a symbol including definition, callers, and callees."""
        symbols = self.graph.get('symbols', {})
        edges = self.graph.get('edges', [])
        
        if symbol_name not in symbols:
            # Try fuzzy match
            matches = [s for s in symbols.keys() if symbol_name.lower() in s.lower()]
            if matches:
                symbol_name = matches[0]
            else:
                return {"error": f"Symbol '{symbol_name}' not found"}
        
        symbol = symbols[symbol_name]
        
        # Find callers (who calls this symbol)
        callers = []
        for edge in edges:
            if edge.get('target') == symbol_name and edge.get('type') == 'CALLS':
                callers.append(edge.get('source'))
        
        # Find callees (who this symbol calls)
        callees = []
        for edge in edges:
            if edge.get('source') == symbol_name and edge.get('type') == 'CALLS':
                callees.append(edge.get('target'))
        
        return {
            "definition": {
                "name": symbol.get("name"),
                "type": symbol.get("type"),
                "file": symbol.get("file"),
                "line_start": symbol.get("line_start"),
                "return_type": symbol.get("return_type"),
                "parameters": symbol.get("parameters")
            },
            "callers": list(set(callers)),
            "callees": list(set(callees))
        }
    
    def impact_analysis(self, symbol_name: str) -> Dict[str, Any]:
        """Analyze what would be impacted if a symbol changes."""
        edges = self.graph.get('edges', [])
        symbols = self.graph.get('symbols', {})
        
        if symbol_name not in symbols:
            return {"error": f"Symbol '{symbol_name}' not found"}
        
        # Find all dependents
        dependents = []
        for edge in edges:
            if edge.get('target') == symbol_name:
                dependents.append({
                    "symbol": edge.get('source'),
                    "relationship": edge.get('type')
                })
        
        # Get symbol info
        symbol = symbols[symbol_name]
        
        return {
            "symbol": symbol_name,
            "type": symbol.get("type"),
            "file": symbol.get("file"),
            "dependents_count": len(dependents),
            "dependents": dependents[:50]  # Limit results
        }
    
    def trace_execution_flow(self, start: str, end: str) -> Dict[str, Any]:
        """Find execution path between two symbols using BFS."""
        edges = self.graph.get('edges', [])
        
        # Build adjacency list
        adj: Dict[str, List[str]] = {}
        for edge in edges:
            if edge.get('type') == 'CALLS':
                src = edge.get('source', '')
                tgt = edge.get('target', '')
                if src not in adj:
                    adj[src] = []
                adj[src].append(tgt)
        
        # BFS
        from collections import deque
        queue = deque([(start, [start])])
        visited = {start}
        
        while queue:
            current, path = queue.popleft()
            
            if current == end:
                return {
                    "found": True,
                    "path": path,
                    "length": len(path)
                }
            
            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        
        return {
            "found": False,
            "message": f"No path found from '{start}' to '{end}'"
        }
    
    def get_file_summary(self, file_path: str) -> Dict[str, Any]:
        """Get summary of symbols in a file."""
        symbols = self.graph.get('symbols', {})
        files = self.graph.get('files', {})
        
        # Find matching file
        matched_file = None
        for fp in files.keys():
            if file_path in fp or fp.endswith(file_path):
                matched_file = fp
                break
        
        if not matched_file:
            return {"error": f"File '{file_path}' not found"}
        
        # Get symbols in this file
        file_symbols = [
            {
                "name": s.get("name"),
                "type": s.get("type"),
                "line_start": s.get("line_start")
            }
            for s in symbols.values()
            if s.get("file") == matched_file
        ]
        
        file_info = files.get(matched_file, {})
        
        return {
            "file": matched_file,
            "name": file_info.get("name", ""),
            "lines": file_info.get("lines", 0),
            "size": file_info.get("size", 0),
            "symbols_count": len(file_symbols),
            "symbols": sorted(file_symbols, key=lambda x: x.get("line_start", 0))
        }
    
    def search_symbols(self, query: str) -> Dict[str, Any]:
        """Search symbols by name or type."""
        symbols = self.graph.get('symbols', {})
        
        query_lower = query.lower()
        results = []
        
        for name, symbol in symbols.items():
            # Match in name, type, or file
            if (query_lower in name.lower() or
                query_lower in symbol.get('type', '').lower() or
                query_lower in symbol.get('file', '').lower()):
                results.append({
                    "name": name,
                    "type": symbol.get("type"),
                    "file": symbol.get("file"),
                    "line_start": symbol.get("line_start")
                })
        
        return {
            "query": query,
            "results_count": len(results),
            "results": results[:100]  # Limit results
        }
    
    def resolve_includes(self, file_path: str) -> Dict[str, Any]:
        """Resolve includes for a file recursively."""
        includes = self.graph.get('includes', {})
        
        # Find matching file
        matched_file = None
        for fp in includes.keys():
            if file_path in fp or fp.endswith(file_path):
                matched_file = fp
                break
        
        if not matched_file:
            return {"error": f"File '{file_path}' not found"}
        
        resolved = []
        visited = set()
        
        def resolve_recursive(fp: str, depth: int = 0):
            if fp in visited or depth > 10:  # Prevent infinite loops
                return
            visited.add(fp)
            
            for inc in includes.get(fp, []):
                resolved.append({"file": fp, "includes": inc, "depth": depth})
                resolve_recursive(inc, depth + 1)
        
        resolve_recursive(matched_file)
        
        return {
            "file": matched_file,
            "resolved_includes": resolved,
            "circular_dependency": len(visited) != len(resolved)
        }
    
    async def run(self):
        """Run the MCP server."""
        if not MCP_AVAILABLE:
            print("Error: MCP library not installed. Run: pip install mcp", file=sys.stderr)
            sys.exit(1)
        
        if not self.server:
            print("Error: Server not initialized", file=sys.stderr)
            sys.exit(1)
        
        print(f"MQL5 Knowledge Graph MCP Server starting...", file=sys.stderr)
        print(f"Graph path: {self.graph_path}", file=sys.stderr)
        
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def create_server(graph_path: str = 'graph.json') -> MCPServer:
    """Create an MCP server instance."""
    return MCPServer(graph_path)
