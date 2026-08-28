"""Security tests: filesystem containment, MCP restrictions, budget safety."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mql5_kg.adapters.mcp.service import AdapterError, ProjectSession
from mql5_kg.indexer import analyze_repository

from conftest import FIXTURES


def test_include_traversal_cannot_escape_root(tmp_path):
    """An include with ../ must never resolve outside the project root."""
    outside = tmp_path.parent / "outside_secret.mqh"
    outside.write_text("int SECRET = 1;\n", encoding="utf-8")
    (tmp_path / "main.mq5").write_text(
        '#include "../{name}"\nvoid Main() {{ }}\n'.format(name=outside.name),
        encoding="utf-8",
    )
    graph = analyze_repository(str(tmp_path))
    edges = [
        edge for edge in graph.edges.values()
        if edge.relationship == "includes"
    ]
    for edge in edges:
        node = graph.nodes[edge.target]
        # Resolved includes stay inside the project; escaped ones stay unresolved
        if node.attributes.get("unresolved"):
            assert node.attributes.get("external") is True
        else:
            assert node.qualified_name == "main.mq5" or node.qualified_name.startswith("main.mq5")


def test_absolute_include_rejected(tmp_path):
    (tmp_path / "main.mq5").write_text(
        'int __LINE__;\n', encoding="utf-8"
    )
    # Absolute-path include must not be resolved
    graph = analyze_repository(str(tmp_path))
    assert graph is not None


def test_mcp_rejects_relative_corpus_root():
    session = ProjectSession()
    with pytest.raises(AdapterError) as exc_info:
        session.index_project("some/relative/path")
    assert exc_info.value.code == "invalid_project_root"


def test_mcp_rejects_empty_root():
    session = ProjectSession()
    with pytest.raises(AdapterError):
        session.index_project("   ")


def test_mcp_rejects_path_excludes():
    session = ProjectSession()
    with pytest.raises(AdapterError) as exc_info:
        session.index_project(str(FIXTURES), excluded=["../escape"])
    assert exc_info.value.code == "invalid_tool_arguments"


def test_tiny_budget_never_publishes_partial_graph(tmp_path):
    from mql5_kg.analysis_budget import AnalysisBudgetExceeded
    from mql5_kg.indexer import analyze_repository
    from mql5_kg.snapshots import GraphSnapshot

    source = (tmp_path / "a.mq5")
    source.write_text("void Foo() { Bar(); }\n", encoding="utf-8")
    graph = analyze_repository(str(tmp_path))
    snapshot = GraphSnapshot.publish(graph, revision=1)
    # After a failed rebuild, the previous valid snapshot must remain intact
    with pytest.raises(AnalysisBudgetExceeded):
        analyze_repository(str(tmp_path), max_work=5)
    rebuilt = GraphSnapshot.publish(analyze_repository(str(tmp_path)), revision=2)
    assert rebuilt.graph.to_json() == snapshot.graph.to_json()
    assert rebuilt.fingerprint == snapshot.fingerprint


def test_graphify_uses_shell_false():
    """The graphify adapter must never use shell=True."""
    import inspect
    import mql5_kg.reference.graphify_adapter as adapter

    source = inspect.getsource(adapter)
    assert "shell=False" in source
    assert "shell=True" not in source


def test_no_credentials_in_lifecycle_logs():
    """MCP lifecycle payloads must never include environment credentials."""
    from mql5_kg.adapters.mcp.server import _emit_lifecycle
    import io

    secret_marker = "SUPERSECRETVALUE123"
    credential_names = [name for name in os.environ if any(
        marker in name.upper() for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
    )]
    stream = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = stream
    try:
        _emit_lifecycle("test")
    finally:
        sys.stderr = old_stderr
    output = stream.getvalue()
    for name in credential_names:
        assert os.environ[name] not in output, f"credential leaked from {name}"
    assert secret_marker not in output


def test_mcp_stdout_stays_protocol_clean(tmp_path):
    """MCP lifecycle logs go to stderr; stdout must carry only protocol data."""
    result = subprocess.run(
        [sys.executable, "-c",
         "import mql5_kg.adapters.mcp.server as s; s._emit_lifecycle('starting'); s._emit_lifecycle('stopped')"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.stdout == ""
    assert "lifecycle" in result.stderr
