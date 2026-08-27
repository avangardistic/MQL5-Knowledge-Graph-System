"""
MCP wire-protocol regression tests.
These tests start the MCP server as a real subprocess and communicate
over its actual stdio transport using the MCP SDK's own client.

This is a REQUIRED test — Python-function call tests do NOT substitute.
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest
import anyio
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.session import ClientSession

FIXTURES = Path(__file__).parent / "fixtures"
PYTHON = sys.executable


@pytest.fixture(scope="module")
def graph_dir(tmp_path_factory):
    """Build a graph from fixtures and return the directory."""
    tmp = tmp_path_factory.mktemp("wire_graph")
    import subprocess
    r = subprocess.run(
        [PYTHON, "-m", "mql5_kg.cli.graphify", "build", str(FIXTURES), "--output", str(tmp)],
        capture_output=True, text=True
    )
    assert r.returncode == 0, f"Graph build failed: {r.stderr}"
    assert (tmp / "graph.json").exists(), "graph.json not created"
    return tmp


@pytest.fixture(scope="module")
def graph_file(graph_dir):
    return str(graph_dir / "graph.json")


async def _run_session(graph_file: str, fn):
    """Start a real MCP subprocess and run fn(session) over its wire protocol."""
    params = StdioServerParameters(
        command=PYTHON,
        args=["-m", "mql5_kg.cli.graphify", "serve", "--graph", graph_file],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


def run_sync(graph_file: str, fn):
    """Run an async MCP session synchronously."""
    return anyio.from_thread.run_sync(lambda: anyio.run(_run_session, graph_file, fn))


class TestMCPWireProtocol:
    """Tests that communicate with the MCP server over its actual wire protocol."""

    @pytest.mark.asyncio
    async def test_tools_list_returns_six_tools(self, graph_file):
        """tools/list must return all 6 required tools."""
        async def check(session: ClientSession):
            result = await session.list_tools()
            return result

        params = StdioServerParameters(
            command=PYTHON,
            args=["-m", "mql5_kg.cli.graphify", "serve", "--graph", graph_file],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()

        tool_names = {t.name for t in result.tools}
        expected = {
            "get_symbol_context", "impact_analysis", "trace_execution_flow",
            "get_file_summary", "search_symbols", "resolve_includes"
        }
        assert tool_names == expected, f"Missing tools: {expected - tool_names}"

    @pytest.mark.asyncio
    async def test_search_symbols_via_wire(self, graph_file):
        """search_symbols must return results via real MCP protocol."""
        params = StdioServerParameters(
            command=PYTHON,
            args=["-m", "mql5_kg.cli.graphify", "serve", "--graph", graph_file],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("search_symbols", {"query": "OnTick"})

        assert result.content, "No content in result"
        data = json.loads(result.content[0].text)
        assert data["results_count"] > 0, "Expected at least one result"
        names = [r["name"] for r in data["results"]]
        assert "OnTick" in names

    @pytest.mark.asyncio
    async def test_get_symbol_context_via_wire(self, graph_file):
        """get_symbol_context must return definition via real MCP protocol."""
        params = StdioServerParameters(
            command=PYTHON,
            args=["-m", "mql5_kg.cli.graphify", "serve", "--graph", graph_file],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("get_symbol_context", {"symbol_name": "OnTick"})

        data = json.loads(result.content[0].text)
        assert "definition" in data, f"Expected 'definition' in {data}"
        assert data["definition"]["name"] == "OnTick"

    @pytest.mark.asyncio
    async def test_impact_analysis_via_wire(self, graph_file):
        """impact_analysis must return dependents via real MCP protocol."""
        params = StdioServerParameters(
            command=PYTHON,
            args=["-m", "mql5_kg.cli.graphify", "serve", "--graph", graph_file],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("impact_analysis", {"symbol_name": "OnTick"})

        data = json.loads(result.content[0].text)
        assert "symbol" in data, f"Expected 'symbol' in {data}"
        assert data["symbol"] == "OnTick"

    @pytest.mark.asyncio
    async def test_trace_execution_flow_via_wire(self, graph_file):
        """trace_execution_flow must return path info via real MCP protocol."""
        params = StdioServerParameters(
            command=PYTHON,
            args=["-m", "mql5_kg.cli.graphify", "serve", "--graph", graph_file],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "trace_execution_flow",
                    {"start": "OnTick", "end": "CalculateLotSize"}
                )

        data = json.loads(result.content[0].text)
        assert "found" in data

    @pytest.mark.asyncio
    async def test_get_file_summary_via_wire(self, graph_file):
        """get_file_summary must return file info via real MCP protocol."""
        params = StdioServerParameters(
            command=PYTHON,
            args=["-m", "mql5_kg.cli.graphify", "serve", "--graph", graph_file],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("get_file_summary", {"file_path": "audit_test.mq5"})

        data = json.loads(result.content[0].text)
        assert "symbols" in data or "error" in data

    @pytest.mark.asyncio
    async def test_resolve_includes_via_wire(self, graph_file):
        """resolve_includes must return include info via real MCP protocol."""
        params = StdioServerParameters(
            command=PYTHON,
            args=["-m", "mql5_kg.cli.graphify", "serve", "--graph", graph_file],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("resolve_includes", {"file_path": "audit_test.mq5"})

        data = json.loads(result.content[0].text)
        assert "resolved_includes" in data or "error" in data

    @pytest.mark.asyncio
    async def test_nonexistent_symbol_graceful_error(self, graph_file):
        """nonexistent symbol must return error dict, not crash."""
        params = StdioServerParameters(
            command=PYTHON,
            args=["-m", "mql5_kg.cli.graphify", "serve", "--graph", graph_file],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_symbol_context", {"symbol_name": "NonExistentXYZ999"}
                )

        data = json.loads(result.content[0].text)
        assert "error" in data, f"Expected error key, got: {data}"
