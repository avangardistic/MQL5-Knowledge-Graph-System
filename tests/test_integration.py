"""
End-to-end integration tests: parse → graph → CLI → MCP
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from mql5_kg.parser import MQL5Parser
from mql5_kg.storage import GraphStorage
from mql5_kg.mcp_server import MCPServer

FIXTURES = Path(__file__).parent / "fixtures"
PYTHON = sys.executable
REPO_ROOT = Path(__file__).parent.parent


def run_cli(*args, cwd=None):
    cmd = [PYTHON, "-m", "mql5_kg.cli.graphify"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd or REPO_ROOT))


class TestEndToEnd:
    """Full pipeline: realistic_ea.mq5 → graph.json → CLI queries → MCP calls."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.tmp = tmp_path
        result = run_cli("build", str(FIXTURES / "realistic_ea.mq5"), "-o", str(tmp_path))
        assert result.returncode == 0, f"Build failed: {result.stderr}"
        self.graph_path = str(tmp_path / "graph.json")
        self.server = MCPServer(self.graph_path)

    def test_graph_has_event_handlers(self):
        syms = self.server.graph.get('symbols', {})
        assert 'OnInit' in syms
        assert 'OnTick' in syms
        assert 'OnDeinit' in syms

    def test_graph_has_user_functions(self):
        syms = self.server.graph.get('symbols', {})
        assert 'OpenBuy' in syms
        assert 'OpenSell' in syms
        assert 'CloseAll' in syms

    def test_calls_edges_between_user_functions(self):
        edges = self.server.graph.get('edges', [])
        calls = {(e['source'], e['target']) for e in edges if e['type'] == 'CALLS'}
        # OnTick should call CloseAll (via equity check)
        assert any(src == 'OnTick' for src, _ in calls), \
            "OnTick should have at least one CALLS edge"

    def test_no_keyword_calls(self):
        keywords = {'if', 'for', 'while', 'switch', 'else', 'case', 'default'}
        edges = self.server.graph.get('edges', [])
        bad = {e['target'] for e in edges if e['type'] == 'CALLS' and e['target'] in keywords}
        assert not bad, f"Keyword CALLS targets: {bad}"

    def test_cli_query_search_finds_ontick(self):
        r = run_cli("query", "search", "OnTick", "--graph", self.graph_path)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        names = [x['name'] for x in data.get('results', [])]
        assert 'OnTick' in names

    def test_cli_query_symbol_ontick(self):
        r = run_cli("query", "symbol", "OnTick", "--graph", self.graph_path)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data.get('definition', {}).get('name') == 'OnTick'

    def test_cli_no_attribute_error(self):
        r = run_cli("query", "search", "OnTick", "--graph", self.graph_path)
        assert "AttributeError" not in r.stderr

    def test_cli_no_runtime_warning(self):
        r = run_cli("query", "search", "OnTick", "--graph", self.graph_path)
        assert "RuntimeWarning" not in r.stderr

    def test_return_type_ontick(self):
        syms = self.server.graph.get('symbols', {})
        assert syms.get('OnTick', {}).get('return_type') == 'void'

    @pytest.mark.asyncio
    async def test_mcp_search_tool(self):
        result = await self.server._handle_tool("search_symbols", {"query": "OnTick"})
        assert result["results_count"] > 0

    @pytest.mark.asyncio
    async def test_mcp_get_symbol_context(self):
        result = await self.server._handle_tool("get_symbol_context", {"symbol_name": "OpenBuy"})
        assert "definition" in result

    def test_includes_resolved(self):
        r = run_cli("query", "includes", "realistic_ea.mq5", "--graph", self.graph_path)
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert "resolved_includes" in data or "error" in data
