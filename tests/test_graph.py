"""
Tests for graph storage and graph integrity after a full build.
"""

import json
import tempfile
import shutil
from pathlib import Path

import pytest

from mql5_kg.parser import MQL5Parser
from mql5_kg.storage import GraphStorage

FIXTURES = Path(__file__).parent / "fixtures"


def build_graph_from(fixture_name: str, tmp_dir: str) -> dict:
    p = MQL5Parser()
    p.parse_file(str(FIXTURES / fixture_name))
    graph = p.get_graph()
    storage = GraphStorage(tmp_dir)
    storage.save_graph(graph)
    return graph


class TestGraphStorage:
    def test_save_and_reload(self, tmp_path):
        p = MQL5Parser()
        p.parse_file(str(FIXTURES / "audit_test.mq5"))
        graph = p.get_graph()
        storage = GraphStorage(str(tmp_path))
        path = storage.save_graph(graph)
        reloaded = storage.load_graph()

        assert 'symbols' in reloaded
        assert 'edges' in reloaded
        assert 'files' in reloaded
        assert 'metadata' in reloaded

    def test_statistics_in_saved_graph(self, tmp_path):
        p = MQL5Parser()
        p.parse_file(str(FIXTURES / "audit_test.mq5"))
        graph = p.get_graph()
        storage = GraphStorage(str(tmp_path))
        storage.save_graph(graph)
        reloaded = storage.load_graph()
        stats = reloaded.get('statistics', {})
        assert stats.get('total_symbols', 0) > 0
        assert stats.get('total_edges', 0) > 0

    def test_report_generation(self, tmp_path):
        p = MQL5Parser()
        p.parse_file(str(FIXTURES / "audit_test.mq5"))
        graph = p.get_graph()
        storage = GraphStorage(str(tmp_path))
        report_path = storage.generate_report(graph)
        assert Path(report_path).exists()
        content = Path(report_path).read_text(encoding='utf-8')
        assert 'MQL5 Knowledge Graph Report' in content


class TestGraphIntegrityAfterBuild:
    """Validate graph.json produced from the test corpus."""

    def test_no_numeric_symbol_keys(self, tmp_path):
        graph = build_graph_from("audit_test.mq5", str(tmp_path))
        storage = GraphStorage(str(tmp_path))
        saved = storage.load_graph()
        for name in saved.get('symbols', {}):
            try:
                float(name)
                pytest.fail(f"Numeric symbol key found: {name!r}")
            except ValueError:
                pass

    def test_no_keyword_calls_targets(self, tmp_path):
        KEYWORDS = {'if', 'for', 'while', 'switch', 'else', 'case', 'default'}
        graph = build_graph_from("audit_test.mq5", str(tmp_path))
        storage = GraphStorage(str(tmp_path))
        saved = storage.load_graph()
        for edge in saved.get('edges', []):
            if edge.get('type') == 'CALLS':
                assert edge.get('target') not in KEYWORDS, \
                    f"Keyword {edge['target']!r} in CALLS edges"

    def test_edge_nodes_exist_as_symbols_or_files(self, tmp_path):
        graph = build_graph_from("audit_test.mq5", str(tmp_path))
        storage = GraphStorage(str(tmp_path))
        saved = storage.load_graph()
        sym_keys = set(saved.get('symbols', {}).keys())
        file_keys = set(saved.get('files', {}).keys())
        all_nodes = sym_keys | file_keys

        for edge in saved.get('edges', []):
            if edge.get('type') == 'CALLS':
                assert edge['source'] in all_nodes
                assert edge['target'] in all_nodes
