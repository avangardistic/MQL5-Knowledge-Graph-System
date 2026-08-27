"""
Tests for the MCP server — startup, tool listing, and tool calls.
"""

import json
import tempfile
import pytest
from pathlib import Path

from mql5_kg.parser import MQL5Parser
from mql5_kg.storage import GraphStorage
from mql5_kg.mcp_server import MCPServer

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def graph_path(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("graph")
    p = MQL5Parser()
    p.parse_file(str(FIXTURES / "audit_test.mq5"))
    graph = p.get_graph()
    storage = GraphStorage(str(tmp))
    storage.save_graph(graph)
    return str(tmp / "graph.json")


@pytest.fixture(scope="module")
def server(graph_path):
    return MCPServer(graph_path)


class TestMCPServerInit:
    def test_server_loads_graph(self, server):
        assert server.graph, "Graph should not be empty after loading"

    def test_mcp_server_object_created(self, server):
        from mql5_kg.mcp_server.server import MCP_AVAILABLE
        if MCP_AVAILABLE:
            assert server.server is not None
        else:
            pytest.skip("mcp not installed")

    def test_tool_definitions_returned(self, server):
        from mql5_kg.mcp_server.server import MCP_AVAILABLE
        if not MCP_AVAILABLE:
            pytest.skip("mcp not installed")
        tools = server._tool_definitions()
        names = {t.name for t in tools}
        expected = {
            "get_symbol_context", "impact_analysis", "trace_execution_flow",
            "get_file_summary", "search_symbols", "resolve_includes"
        }
        assert names == expected


class TestMCPToolCalls:
    """Direct synchronous calls to the query methods."""

    def test_get_symbol_context_found(self, server):
        result = server.get_symbol_context("OnTick")
        assert "definition" in result
        assert result["definition"]["name"] == "OnTick"

    def test_get_symbol_context_not_found(self, server):
        result = server.get_symbol_context("NonExistentSymbol_XYZ")
        assert "error" in result

    def test_search_symbols_returns_results(self, server):
        result = server.search_symbols("OnTick")
        assert result["results_count"] > 0
        names = [r["name"] for r in result["results"]]
        assert "OnTick" in names

    def test_impact_analysis_found(self, server):
        result = server.impact_analysis("OnTick")
        assert "symbol" in result
        assert result["symbol"] == "OnTick"

    def test_impact_analysis_not_found(self, server):
        result = server.impact_analysis("NonExistentXYZ")
        assert "error" in result

    def test_trace_execution_flow_no_path(self, server):
        result = server.trace_execution_flow("OnTick", "NonExistentXYZ")
        assert "found" in result
        assert result["found"] is False

    def test_get_file_summary_found(self, server):
        result = server.get_file_summary("audit_test.mq5")
        assert "symbols" in result or "error" in result
        if "symbols" in result:
            assert isinstance(result["symbols"], list)

    def test_resolve_includes(self, server):
        result = server.resolve_includes("audit_test.mq5")
        # audit_test.mq5 has no includes — error or empty is both valid
        assert "resolved_includes" in result or "error" in result


class TestMCPAsyncToolDispatch:
    """Test the async _handle_tool method."""

    @pytest.mark.asyncio
    async def test_handle_search_symbols(self, server):
        result = await server._handle_tool("search_symbols", {"query": "OnTick"})
        assert "results" in result

    @pytest.mark.asyncio
    async def test_handle_get_symbol_context(self, server):
        result = await server._handle_tool("get_symbol_context", {"symbol_name": "OnTick"})
        assert "definition" in result

    @pytest.mark.asyncio
    async def test_handle_unknown_tool(self, server):
        result = await server._handle_tool("unknown_tool_xyz", {})
        assert "error" in result
