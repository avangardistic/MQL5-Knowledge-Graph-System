"""Diagnostics tests: coded diagnostics do not corrupt graph construction."""

from mql5_kg.diagnostics import (
    AMBIGUOUS_CALL,
    DECODE_RECOVERY,
    Diagnostic,
    GRAPH_VALIDATION,
    UNMATCHED_DELIMITER,
    UNRESOLVED_CALL,
    UNRESOLVED_INCLUDE,
    UNTERMINATED_COMMENT,
    UNTERMINATED_STRING,
)
from mql5_kg.graph import SourceLocation
from mql5_kg.indexer import analyze_repository

from conftest import ADVERSARIAL, FIXTURES


def test_required_diagnostic_codes_exist():
    for code in (
        UNTERMINATED_STRING,
        UNTERMINATED_COMMENT,
        UNMATCHED_DELIMITER,
        UNRESOLVED_INCLUDE,
        AMBIGUOUS_CALL,
        UNRESOLVED_CALL,
        DECODE_RECOVERY,
        GRAPH_VALIDATION,
    ):
        assert code.startswith(("LEX", "PARSE", "RESOLVE", "SOURCE", "GRAPH"))


def test_diagnostic_dict_round_trip():
    diagnostic = Diagnostic(
        UNRESOLVED_INCLUDE,
        "warning",
        "Unable to resolve include 'x.mqh'",
        SourceLocation("a.mq5", 3, 1),
    )
    restored = Diagnostic.from_dict(diagnostic.to_dict())
    assert restored == diagnostic


def test_diagnostics_do_not_corrupt_graph(tmp_path):
    (tmp_path / "broken.mq5").write_text(
        (ADVERSARIAL / "adversarial_broken.mq5").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    graph = analyze_repository(str(tmp_path))
    assert graph.nodes
    assert any(d.code == UNMATCHED_DELIMITER for d in graph.diagnostics)


def test_fixture_diagnostics_present():
    graph = analyze_repository(str(FIXTURES))
    assert len(graph.diagnostics) > 0
