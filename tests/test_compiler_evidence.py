"""Compiler evidence tests: read-only correlation, staleness, containment."""

import shutil
from pathlib import Path

import pytest

from mql5_kg.compiler_evidence import (
    CompilerEvidenceError,
    correlate_compiler_log,
    correlation_result,
)
from mql5_kg.indexer import analyze_repository
from mql5_kg.intelligence import IntelligenceKernel

FIXTURES = Path(__file__).parent / "fixtures"
LOGS = FIXTURES / "compiler_logs"
BASIC_EA = FIXTURES / "basic_ea"


@pytest.fixture()
def project(tmp_path):
    """A project root containing the EA sources AND the compiler logs (logs must
    stay under the analyzed root by security design)."""
    for source in BASIC_EA.iterdir():
        shutil.copy2(source, tmp_path / source.name)
    for log in LOGS.iterdir():
        shutil.copy2(log, tmp_path / log.name)
    return tmp_path


@pytest.fixture()
def graph(project):
    return analyze_repository(str(project))


def test_success_log_correlation(graph, project):
    report = correlate_compiler_log(
        graph, str(project), "basic-success.log", "BasicEA.mq5"
    )
    assert report.entry_file == "BasicEA.mq5"
    assert report.log_fingerprint
    assert report.evidence_state in {"current", "stale", "incomplete"}


def test_errors_log_correlation(graph, project):
    report = correlate_compiler_log(
        graph, str(project), "basic-errors.log", "BasicEA.mq5"
    )
    assert report.diagnostics
    located = [d for d in report.diagnostics if d.location is not None]
    assert located


def test_graph_is_not_mutated(graph, project):
    before = graph.to_json()
    correlate_compiler_log(graph, str(project), "basic-success.log", "BasicEA.mq5")
    assert graph.to_json() == before


def test_result_envelope(graph, project):
    report = correlate_compiler_log(
        graph, str(project), "basic-warnings.log", "BasicEA.mq5"
    )
    kernel = IntelligenceKernel(graph, snapshot_revision=1)
    envelope = correlation_result(report, kernel.graph_identity)
    assert envelope["contract_version"] == "1.0.0"
    assert envelope["graph_identity"]["snapshot_revision"] == 1


def test_log_outside_root_rejected(graph, project, tmp_path):
    outside = tmp_path.parent / "secret.log"
    outside.write_text("stuff", encoding="utf-8")
    with pytest.raises(CompilerEvidenceError) as exc_info:
        correlate_compiler_log(graph, str(project), str(outside), "BasicEA.mq5")
    assert exc_info.value.code == "compiler_log_outside_root"


def test_entry_must_be_mq5(graph, project):
    with pytest.raises(CompilerEvidenceError) as exc_info:
        correlate_compiler_log(graph, str(project), "basic-success.log", "Risk.mqh")
    assert exc_info.value.code == "compiler_log_invalid"


def test_missing_log_rejected(graph, project):
    with pytest.raises(CompilerEvidenceError):
        correlate_compiler_log(graph, str(project), "missing.log", "BasicEA.mq5")
