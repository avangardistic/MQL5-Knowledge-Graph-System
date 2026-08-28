"""MCP adapter tests: service-level behavior and real wire-protocol checks."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from mql5_kg.adapters.mcp.service import AdapterError, ProjectSession, ReferenceSession

FIXTURES = Path(__file__).parent / "fixtures"
PYTHON = sys.executable

MCP_MODULE = "mql5_kg.adapters.mcp.server"

try:
    import mcp  # noqa: F401
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


@pytest.fixture()
def session() -> ProjectSession:
    return ProjectSession()


class TestProjectSession:
    def test_not_indexed_status(self, session):
        status = session.project_status()
        assert status["status"] == "not_indexed"

    def test_index_project(self, session):
        result = session.index_project(str(FIXTURES))
        assert result["status"] == "indexed"
        assert result["counts"]["nodes"] > 0
        assert result["graph_identity"]["snapshot_revision"] == 1

    def test_reindex_reuses_snapshot(self, session):
        session.index_project(str(FIXTURES))
        second = session.index_project(str(FIXTURES))
        assert second["reused"] is True

    def test_invalid_root_rejected(self, session):
        with pytest.raises(AdapterError) as exc_info:
            session.index_project("/does/not/exist")
        assert exc_info.value.code == "invalid_project_root"

    def test_intelligence_before_index_fails(self, session):
        with pytest.raises(AdapterError) as exc_info:
            session.query_symbols("OnTick")
        assert exc_info.value.code == "project_not_indexed"

    def test_query_symbols(self, session):
        session.index_project(str(FIXTURES))
        result = session.query_symbols("CalculateLotSize")
        assert result["resolution"][0]["status"] == "matched"

    def test_ambiguity_preserved(self, session):
        session.index_project(str(FIXTURES))
        result = session.query_symbols("OnTick")
        assert result["resolution"][0]["status"] == "ambiguous"

    def test_context_package(self, session):
        session.index_project(str(FIXTURES))
        result = session.get_context_package("CloseAllPositions", context_units=40)
        package = result["context_package"]
        assert package["budget_used"] <= package["budget_limit"]

    def test_fingerprint_mismatch(self, session):
        session.index_project(str(FIXTURES))
        with pytest.raises(AdapterError) as exc_info:
            session.query_symbols("OnTick", expected_source_fingerprint="wrong")
        assert exc_info.value.code == "intelligence_error"
        assert "graph_identity_mismatch" in exc_info.value.details["intelligence_error"]["code"]

    def test_excluded_must_be_dir_names(self, session):
        with pytest.raises(AdapterError) as exc_info:
            session.index_project(str(FIXTURES), excluded=["a/b"])
        assert exc_info.value.code == "invalid_tool_arguments"

    def test_tiny_budget_fails_safely(self, session):
        with pytest.raises(AdapterError) as exc_info:
            session.index_project(str(FIXTURES), max_work=5)
        assert exc_info.value.code == "analysis_budget_exceeded"
        assert "not_model_token_limit" in exc_info.value.details


@pytest.mark.skipif(not MCP_AVAILABLE, reason="mcp package not installed")
class TestMCPWireProtocol:
    async def _session(self, fn):
        params = StdioServerParameters(command=PYTHON, args=["-m", MCP_MODULE])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await fn(session)

    @pytest.mark.asyncio
    async def test_tools_listed(self):
        async def check(session):
            result = await session.list_tools()
            return {tool.name for tool in result.tools}

        tool_names = await self._session(check)
        assert "project_status" in tool_names
        assert "index_project" in tool_names
        assert "get_symbol_context" in tool_names  # legacy name preserved
        assert "impact_analysis" in tool_names
        assert "trace_execution_flow" in tool_names
        assert "get_context_package" in tool_names

    @pytest.mark.asyncio
    async def test_index_and_query_round_trip(self):
        async def check(session):
            await session.call_tool("index_project", {"root": str(FIXTURES)})
            result = await session.call_tool("search_symbols", {"query": "OnTick"})
            return json.loads(result.content[0].text)

        data = await self._session(check)
        assert data["resolution"][0]["status"] in {"matched", "ambiguous"}

    @pytest.mark.asyncio
    async def test_context_package_via_wire(self):
        async def check(session):
            await session.call_tool("index_project", {"root": str(FIXTURES)})
            result = await session.call_tool(
                "get_context_package", {"target": "CloseAllPositions", "context_units": 30}
            )
            return json.loads(result.content[0].text)

        data = await self._session(check)
        package = data["context_package"]
        assert package["budget_used"] <= package["budget_limit"]

    @pytest.mark.asyncio
    async def test_error_envelope_via_wire(self):
        async def check(session):
            result = await session.call_tool("index_project", {"root": "/does/not/exist"})
            assert result.isError
            # FastMCP prefixes tool errors; the machine-readable envelope is the
            # JSON tail of the error content.
            text = result.content[0].text
            envelope_start = text.index("{")
            return json.loads(text[envelope_start:])

        data = await self._session(check)
        assert data["error"]["code"] == "invalid_project_root"


class TestReferenceSession:
    def test_not_loaded(self):
        session = ReferenceSession()
        assert session.reference_status()["status"] == "not_loaded"

    def test_load_requires_absolute_path(self):
        session = ReferenceSession()
        with pytest.raises(AdapterError) as exc_info:
            session.load_reference_corpus("relative/path")
        assert exc_info.value.code == "invalid_tool_arguments"
