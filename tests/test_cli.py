"""
Tests for the CLI — build and query commands.
"""

import json
import sys
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent
PYTHON = sys.executable


def run_cli(*args, cwd=None) -> subprocess.CompletedProcess:
    """Run the graphify CLI via python -m."""
    cmd = [PYTHON, "-m", "mql5_kg.cli.graphify"] + list(args)
    return subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=str(cwd or REPO_ROOT)
    )


class TestBuildCommand:
    def test_build_creates_graph_json(self, tmp_path):
        result = run_cli("build", str(FIXTURES), "-o", str(tmp_path))
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "graph.json").exists()

    def test_build_output_has_statistics(self, tmp_path):
        run_cli("build", str(FIXTURES), "-o", str(tmp_path))
        graph = json.loads((tmp_path / "graph.json").read_text(encoding='utf-8'))
        stats = graph.get('statistics', {})
        assert stats.get('total_symbols', 0) > 0

    def test_build_single_file(self, tmp_path):
        result = run_cli("build", str(FIXTURES / "audit_test.mq5"), "-o", str(tmp_path))
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "graph.json").exists()

    def test_build_report_flag(self, tmp_path):
        result = run_cli("build", str(FIXTURES), "-o", str(tmp_path), "--report")
        assert result.returncode == 0
        assert (tmp_path / "GRAPH_REPORT.md").exists()

    def test_no_runtime_warning(self, tmp_path):
        result = run_cli("build", str(FIXTURES), "-o", str(tmp_path))
        assert "RuntimeWarning" not in result.stderr, \
            f"RuntimeWarning present: {result.stderr}"


class TestQueryCommands:
    """Query commands require a graph.json built first."""

    @pytest.fixture(autouse=True)
    def build_graph(self, tmp_path):
        run_cli("build", str(FIXTURES), "-o", str(tmp_path))
        self.graph_path = str(tmp_path / "graph.json")
        self.tmp_path = tmp_path

    def run_query(self, *args):
        return run_cli("query", *args, "--graph", self.graph_path)

    def test_query_search(self):
        r = self.run_query("search", "OnTick")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert 'results' in data

    def test_query_symbol(self):
        r = self.run_query("symbol", "OnTick")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert 'definition' in data

    def test_query_impact(self):
        r = self.run_query("impact", "OnTick")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert 'symbol' in data or 'error' in data

    def test_query_file(self):
        r = self.run_query("file", "audit_test.mq5")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert 'symbols' in data or 'error' in data

    def test_query_includes(self):
        r = self.run_query("includes", "realistic_ea.mq5")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert 'resolved_includes' in data or 'error' in data

    def test_query_trace(self):
        r = self.run_query("trace", "OnTick", "CloseAll")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert 'found' in data

    def test_no_attribute_error(self):
        r = self.run_query("search", "OnTick")
        assert "AttributeError" not in r.stderr, f"AttributeError: {r.stderr}"

    def test_no_runtime_warning_on_query(self):
        r = self.run_query("search", "OnTick")
        assert "RuntimeWarning" not in r.stderr, f"RuntimeWarning: {r.stderr}"
