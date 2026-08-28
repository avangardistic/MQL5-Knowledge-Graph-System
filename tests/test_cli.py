"""Tests for the ``mql5kg`` CLI adapter."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
PYTHON = sys.executable


def run_cli(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "mql5_kg.adapters.cli"] + list(args),
        capture_output=True,
        text=True,
        cwd=str(cwd or Path(__file__).parent.parent),
    )


@pytest.fixture(scope="module")
def graph_file(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("kg_cli")
    result = run_cli("index", str(FIXTURES), "-o", str(tmp / "graph.json"))
    assert result.returncode == 0, result.stderr
    return str(tmp / "graph.json")


class TestIndexCommand:
    def test_index_creates_canonical_graph(self, tmp_path):
        result = run_cli("index", str(FIXTURES), "-o", str(tmp_path / "graph.json"))
        assert result.returncode == 0, result.stderr
        graph = json.loads((tmp_path / "graph.json").read_text(encoding="utf-8"))
        assert graph["schema_version"] == "1.0.0"
        assert graph["metadata"]["source_fingerprint"]

    def test_index_json_output(self, tmp_path):
        result = run_cli("index", str(FIXTURES), "-o", str(tmp_path / "graph.json"), "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["nodes"] > 0

    def test_index_missing_root(self):
        result = run_cli("index", "/does/not/exist")
        assert result.returncode == 1


class TestQueryCommands:
    def test_status(self, graph_file):
        result = run_cli("status", graph_file)
        assert result.returncode == 0
        assert "Schema 1.0.0" in result.stdout

    def test_search(self, graph_file):
        result = run_cli("search", graph_file, "OnTick", "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["operation"] == "query"

    def test_symbol(self, graph_file):
        result = run_cli("symbol", graph_file, "CalculateLotSize", "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["resolution"][0]["status"] == "matched"

    def test_callers(self, graph_file):
        result = run_cli("callers", graph_file, "CloseAllPositions")
        assert result.returncode == 0
        assert "OnTick" in result.stdout

    def test_callees(self, graph_file):
        result = run_cli("callees", graph_file, "OnTick", "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        # At max_depth the search space may be flagged as not fully explored;
        # the operation still returns all depth-1 callees.
        assert payload["completion"]["reason"] in {"complete", "max_depth"}
        assert len(payload["relationships"]) > 0

    def test_impact(self, graph_file):
        result = run_cli("impact", graph_file, "CloseAllPositions", "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["operation"] == "impact"

    def test_trace(self, graph_file):
        result = run_cli("trace", graph_file, "OnTick", "CloseAllPositions")
        assert result.returncode == 0
        assert "path 1" in result.stdout

    def test_context_budget(self, graph_file):
        result = run_cli("context", graph_file, "OnTick", "--budget", "40", "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        package = payload["context_package"]
        assert package["budget_used"] <= package["budget_limit"]

    def test_diagnostics(self, graph_file):
        result = run_cli("diagnostics", graph_file, "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert "diagnostics" in payload

    def test_no_match_is_graceful(self, graph_file):
        result = run_cli("symbol", graph_file, "DoesNotExistXYZ")
        assert result.returncode == 0
        assert "no match" in result.stdout


class TestExportCommand:
    def test_export_markdown(self, graph_file, tmp_path):
        result = run_cli("export", graph_file, "--format", "markdown", "-o", str(tmp_path / "report.md"))
        assert result.returncode == 0
        assert (tmp_path / "report.md").exists()

    def test_export_graphml(self, graph_file, tmp_path):
        result = run_cli("export", graph_file, "--format", "graphml", "-o", str(tmp_path / "graph.graphml"))
        assert result.returncode == 0
        content = (tmp_path / "graph.graphml").read_text(encoding="utf-8")
        assert "graphml" in content

    def test_export_json(self, graph_file, tmp_path):
        result = run_cli("export", graph_file, "--format", "json", "-o", str(tmp_path / "graph.json"))
        assert result.returncode == 0
        json.loads((tmp_path / "graph.json").read_text(encoding="utf-8"))
