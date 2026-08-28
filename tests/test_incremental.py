"""Incremental indexing tests: reuse, changed re-parse, determinism, safety.

The central property: an incremental build result is byte-identical (modulo the
``incremental_mode`` metadata tag) to a full rebuild from the same source, and
only truly-changed files are re-parsed.
"""

import json

from mql5_kg.incremental import (
    FileCache,
    incremental_analysis,
    persist_incremental,
)
from mql5_kg.indexer import analyze_repository


def _write(project, name, text):
    path = project / name
    path.write_text(text, encoding="utf-8")
    return path


def _graph_equal_without_mode(a_json: str, b_json: str) -> bool:
    a = json.loads(a_json)
    b = json.loads(b_json)
    for meta in (a["metadata"], b["metadata"]):
        meta.pop("incremental_mode", None)
    return (
        a["nodes"] == b["nodes"]
        and a["edges"] == b["edges"]
        and a["diagnostics"] == b["diagnostics"]
        and a["metadata"] == b["metadata"]
    )


def _tiny_project(tmp_path):
    _write(tmp_path, "a.mq5", "void OnTick() { Foo(); }\nvoid Foo() { Bar(); }\n")
    _write(tmp_path, "b.mq5", "void Bar() { }\nint Dim() { return 1; }\n")
    _write(tmp_path, "c.mq5", "void Baz() { Foo(); }\n")
    return tmp_path


def test_first_run_is_full_and_populates_cache(tmp_path):
    project = _tiny_project(tmp_path)
    result, cache = incremental_analysis(str(project))
    assert result.mode == "full"
    assert result.reused_files == 0
    assert len(cache.records) == 3
    assert result.graph.metadata["incremental_mode"] == "full"
    assert result.graph.metadata["file_count"] == 3


def test_unchanged_run_reuses_everything(tmp_path):
    project = _tiny_project(tmp_path)
    _, cache = incremental_analysis(str(project))
    result, _ = incremental_analysis(str(project), cache=cache)
    assert result.mode == "reuse"
    assert result.reused_files == 3
    assert result.changed_files == ()
    assert result.removed_files == ()


def test_reuse_equals_full_build(tmp_path):
    """The reuse graph must be identical to a fresh full build (Invariant 5)."""
    project = _tiny_project(tmp_path)
    result, cache = incremental_analysis(str(project))
    reused, _ = incremental_analysis(str(project), cache=cache)
    full = analyze_repository(str(project))
    assert _graph_equal_without_mode(reused.graph.to_json(), full.to_json())
    assert _graph_equal_without_mode(result.graph.to_json(), full.to_json())


def test_changed_file_reparsed_and_result_matches_full(tmp_path):
    project = _tiny_project(tmp_path)
    _, cache = incremental_analysis(str(project))
    # Change b.mq5: rename Dim -> Dint (a resolution-relevant change).
    _write(project, "b.mq5", "void Bar() { }\nint Dint() { return 2; }\n")
    result, _ = incremental_analysis(str(project), cache=cache)
    assert result.mode == "incremental"
    assert result.changed_files == ("b.mq5",)
    assert result.reused_files == 2  # a.mq5 + c.mq5 unchanged
    # Incremental result must equal a full rebuild of the changed tree.
    full = analyze_repository(str(project))
    assert _graph_equal_without_mode(result.graph.to_json(), full.to_json())
    # The renamed symbol must actually be re-resolved.
    names = {node.name for node in full.nodes.values()} | {
        node.name for node in result.graph.nodes.values()
    }
    assert "Dint" in names
    assert "Dim" not in names


def test_removed_file_reported_and_graph_updates(tmp_path):
    project = _tiny_project(tmp_path)
    _, cache = incremental_analysis(str(project))
    (project / "c.mq5").unlink()
    result, cache2 = incremental_analysis(str(project), cache=cache)
    assert result.mode == "incremental"
    assert result.removed_files == ("c.mq5",)
    full = analyze_repository(str(project))
    assert _graph_equal_without_mode(result.graph.to_json(), full.to_json())
    # Cache no longer holds a record for the removed file's content.
    assert "Baz" not in {
        node.name for node in result.graph.nodes.values()
    }


def test_added_file_reparsed(tmp_path):
    project = _tiny_project(tmp_path)
    _, cache = incremental_analysis(str(project))
    _write(project, "d.mq5", "void OnStart() { Bar(); }\n")
    result, _ = incremental_analysis(str(project), cache=cache)
    assert result.mode == "incremental"
    assert result.changed_files == ("d.mq5",)
    assert result.reused_files == 3
    full = analyze_repository(str(project))
    assert _graph_equal_without_mode(result.graph.to_json(), full.to_json())


def test_disk_cache_persistence_and_reload(tmp_path):
    project = _tiny_project(tmp_path)
    graph_path = tmp_path / "graph.json"
    cache_path = tmp_path / "graph.cache.json"
    result, cache = incremental_analysis(str(project))
    persist_incremental(result, cache, graph_path=graph_path, cache_path=cache_path)
    assert cache_path.is_file() and graph_path.is_file()

    reloaded_cache = FileCache.load(cache_path)
    assert reloaded_cache.fingerprint == cache.fingerprint
    assert len(reloaded_cache.records) == 3

    # Reload from disk and confirm reuse.
    result2, cache2 = incremental_analysis(str(project), cache_path=cache_path)
    assert result2.mode == "reuse"
    assert result2.reused_files == 3


def test_cache_config_change_falls_back_to_full(tmp_path):
    """Changing config (e.g. include roots) invalidates the cache safely."""
    project = _tiny_project(tmp_path)
    _, cache = incremental_analysis(str(project))
    include_root = tmp_path / "includes"
    include_root.mkdir(exist_ok=True)
    result, new_cache = incremental_analysis(
        str(project), include_roots=[str(include_root)], cache=cache
    )
    # Different config fingerprint => full rebuild, fresh cache.
    assert result.mode == "full"
    assert result.reused_files == 0
    assert new_cache.fingerprint != cache.fingerprint


def test_corrupt_cache_falls_back_to_full(tmp_path):
    """A corrupt cache must not produce a bad graph; it re-parses."""
    project = _tiny_project(tmp_path)
    graph_path = tmp_path / "graph.json"
    cache_path = tmp_path / "graph.cache.json"
    result, cache = incremental_analysis(str(project))
    persist_incremental(result, cache, graph_path=graph_path, cache_path=cache_path)
    # Truncate/corrupt the cache file.
    cache_path.write_text('{"schema":"1.0.0","oops":', encoding="utf-8")
    result2, cache2 = incremental_analysis(str(project), cache_path=cache_path)
    assert result2.mode == "full"
    assert result2.reused_files == 0
    # And it still produces the correct graph.
    full = analyze_repository(str(project))
    assert _graph_equal_without_mode(result2.graph.to_json(), full.to_json())


def test_missing_cache_file_is_full_build(tmp_path):
    project = _tiny_project(tmp_path)
    result, cache = incremental_analysis(
        str(project), cache_path=str(tmp_path / "does-not-exist.json")
    )
    assert result.mode == "full"
    assert len(cache.records) == 3


def test_include_change_ripples_resolution(tmp_path):
    """A changed include must stay correct even though only one file re-parses.

    Resolution runs repository-wide, so a symbol defined in a changed header is
    visible to (and correctly resolves from) unchanged callers. This guards
    the core soundness property of the incremental model.
    """
    _write(tmp_path, "h.mqh", "void Bar() { }\n")
    # a.mq5 (unchanged) calls Bar() zero-arity; h.mqh adds Baz(int).
    _write(tmp_path, "a.mq5", "#include \"h.mqh\"\nvoid OnTick() { Foo(); }\nvoid Foo() { Bar(); }\n")
    # b.mq5 (unchanged) already calls Baz(1) -> unresolved before header gains it.
    _write(tmp_path, "b.mq5", "#include \"h.mqh\"\nvoid Use() { Baz(1); }\n")
    result0, cache = incremental_analysis(str(tmp_path))
    # In the baseline, the call from b.mq5 is unresolved => Baz is external.
    baz0 = [n for n in result0.graph.nodes.values() if n.name == "Baz"]
    assert baz0 and baz0[0].kind == "external_function"
    # Change the header only: add Baz(int).
    _write(tmp_path, "h.mqh", "void Bar() { }\nint Baz(int x) { return x; }\n")
    result, _ = incremental_analysis(str(tmp_path), cache=cache)
    assert result.mode == "incremental"
    assert result.changed_files == ("h.mqh",)
    assert result.reused_files == 2  # a.mq5 + b.mq5 re-parsed from cache
    # The unchanged caller b.mq5 now resolves its call to the new Baz symbol.
    baz_nodes = {node.id for node in result.graph.nodes.values() if node.name == "Baz"}
    assert baz_nodes, "Expected Baz to be present after the header change"
    resolved_to_baz = [
        edge for edge in result.graph.edges.values()
        if edge.relationship == "calls" and edge.target in baz_nodes
    ]
    assert resolved_to_baz, "Expected an unchanged caller to resolve to the new Baz symbol"
    # And the incremental result equals a full rebuild of the changed tree.
    full = analyze_repository(str(tmp_path))
    assert _graph_equal_without_mode(result.graph.to_json(), full.to_json())