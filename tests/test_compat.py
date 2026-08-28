"""Legacy compatibility tests: ``graphify`` CLI and ``MQL5Parser`` facade."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from mql5_kg.compat.legacy_parser import MQL5Parser

FIXTURES = Path(__file__).parent / "fixtures"
PYTHON = sys.executable


def run_legacy(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "mql5_kg.cli.graphify"] + list(args),
        capture_output=True,
        text=True,
        cwd=str(cwd or Path(__file__).parent.parent),
    )


@pytest.fixture(scope="module")
def legacy_graph(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("kg_legacy")
    result = run_legacy("build", str(FIXTURES), "-o", str(tmp))
    assert result.returncode == 0, result.stderr
    return str(tmp / "graph.json")


class TestLegacyBuild:
    def test_build_creates_graph_json(self, tmp_path):
        result = run_legacy("build", str(FIXTURES), "-o", str(tmp_path))
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "graph.json").exists()

    def test_build_report_flag(self, tmp_path):
        result = run_legacy("build", str(FIXTURES), "-o", str(tmp_path), "--report")
        assert result.returncode == 0
        assert (tmp_path / "GRAPH_REPORT.md").exists()


class TestLegacyQueries:
    def test_search(self, legacy_graph):
        result = run_legacy("query", "search", "OnTick", "--graph", legacy_graph)
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert "results" in payload

    def test_symbol(self, legacy_graph):
        result = run_legacy("query", "symbol", "OnTick", "--graph", legacy_graph)
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert "definition" in payload

    def test_impact(self, legacy_graph):
        result = run_legacy("query", "impact", "CloseAllPositions", "--graph", legacy_graph)
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert "symbol" in payload

    def test_trace(self, legacy_graph):
        result = run_legacy("query", "trace", "OnTick", "CloseAllPositions", "--graph", legacy_graph)
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert "found" in payload

    def test_file(self, legacy_graph):
        result = run_legacy("query", "file", "audit_test.mq5", "--graph", legacy_graph)
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert "symbols" in payload

    def test_includes(self, legacy_graph):
        result = run_legacy("query", "includes", "realistic_ea.mq5", "--graph", legacy_graph)
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert "resolved_includes" in payload

    def test_nonexistent_symbol_graceful(self, legacy_graph):
        result = run_legacy("query", "symbol", "NonExistentXYZ999", "--graph", legacy_graph)
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert "error" in payload


class TestLegacyParserFacade:
    def test_parse_file_extracts_symbols(self):
        parser = MQL5Parser()
        result = parser.parse_file(str(FIXTURES / "audit_test.mq5"))
        assert "error" not in result
        assert "OnInit" in parser.symbols
        assert parser.symbols["OnInit"]["type"] == "event_handler"

    def test_return_types(self):
        parser = MQL5Parser()
        parser.parse_file(str(FIXTURES / "return_type_test.mq5"))
        assert parser.symbols["CalculateLotSize"]["return_type"] == "double"

    def test_no_keyword_calls(self):
        parser = MQL5Parser()
        parser.parse_file(str(FIXTURES / "control_flow_test.mq5"))
        targets = {edge["target"] for edge in parser.edges if edge["type"] == "CALLS"}
        assert targets.isdisjoint({"if", "for", "while", "switch", "else", "case", "default", "do"})

    def test_get_graph_shape(self):
        parser = MQL5Parser()
        parser.parse_file(str(FIXTURES / "audit_test.mq5"))
        graph = parser.get_graph()
        assert "symbols" in graph and "edges" in graph and "statistics" in graph
        assert graph["statistics"]["total_symbols"] > 0

    def test_reset(self):
        parser = MQL5Parser()
        parser.parse_file(str(FIXTURES / "audit_test.mq5"))
        assert parser.symbols
        parser.reset()
        assert not parser.symbols
        assert not parser.edges
