"""Canonical graph tests: serialization round-trip, atomic save, determinism."""

import json

from mql5_kg.graph import CodeGraph, GraphEdge, GraphNode, SCHEMA_VERSION, SourceLocation, stable_id
from mql5_kg.indexer import analyze_repository

from conftest import FIXTURES


def test_stable_id_is_deterministic():
    assert stable_id("symbol", "function", "EA.mq5", "OnTick", "OnTick()") == \
        stable_id("symbol", "function", "EA.mq5", "OnTick", "OnTick()")


def test_round_trip(tmp_path):
    graph = analyze_repository(str(FIXTURES))
    path = tmp_path / "graph.json"
    graph.save(path)
    loaded = CodeGraph.load(path)
    assert loaded.to_json() == graph.to_json()


def test_save_is_atomic(tmp_path):
    graph = analyze_repository(str(FIXTURES))
    path = tmp_path / "graph.json"
    graph.save(path)
    assert not path.with_suffix(path.suffix + ".tmp").exists()
    assert path.exists()


def test_schema_version_rejected():
    payload = json.loads(analyze_repository(str(FIXTURES)).to_json())
    payload["schema_version"] = "999.0.0"
    import pytest

    with pytest.raises(ValueError, match="Unsupported graph schema"):
        CodeGraph.from_dict(payload)


def test_serialization_is_deterministic():
    graph = analyze_repository(str(FIXTURES))
    assert graph.to_json() == graph.to_json()


def test_edges_carry_evidence():
    graph = analyze_repository(str(FIXTURES))
    for edge in graph.edges.values():
        assert edge.origin in {"extracted", "resolved", "runtime", "inferred"}
        assert 0.0 <= edge.confidence <= 1.0


def test_metadata_contains_fingerprint():
    graph = analyze_repository(str(FIXTURES))
    assert graph.metadata["source_fingerprint"]
    assert graph.metadata["file_count"] > 0


def test_source_fingerprint_changes_with_source(tmp_path):
    (tmp_path / "a.mq5").write_text("void Foo() { }\n", encoding="utf-8")
    first = analyze_repository(str(tmp_path)).metadata["source_fingerprint"]
    (tmp_path / "a.mq5").write_text("void Foo() { }\nvoid Bar() { }\n", encoding="utf-8")
    second = analyze_repository(str(tmp_path)).metadata["source_fingerprint"]
    assert first != second
