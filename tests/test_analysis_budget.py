"""Analysis budget tests: limits, exhaustion behavior, safe failure."""

import pytest

from mql5_kg.analysis_budget import (
    AnalysisBudget,
    AnalysisBudgetExceeded,
    DEFAULT_MAX_WORK,
    MAX_MAX_WORK,
)
from mql5_kg.indexer import analyze_repository


def test_default_and_maximum_limits():
    assert DEFAULT_MAX_WORK == 1_000_000
    assert MAX_MAX_WORK == 10_000_000


def test_invalid_limits_rejected():
    for bad in (0, -1, MAX_MAX_WORK + 1, True, "10"):
        with pytest.raises(ValueError):
            AnalysisBudget(bad)


def test_consume_tracks_usage():
    budget = AnalysisBudget(10)
    for _ in range(10):
        budget.consume("lexing")
    assert budget.work_used == 10
    with pytest.raises(AnalysisBudgetExceeded):
        budget.consume("parsing")


def test_exceeded_error_is_machine_readable():
    budget = AnalysisBudget(2)
    budget.consume("lexing")
    budget.consume("lexing")
    with pytest.raises(AnalysisBudgetExceeded) as exc_info:
        budget.consume("parsing")
    payload = exc_info.value.to_dict()
    assert payload["code"] == "analysis_budget_exceeded"
    assert payload["details"]["phase"] == "parsing"
    assert payload["details"]["work_limit"] == 2
    assert payload["details"]["not_model_token_limit"] is True


def test_tiny_budget_fails_safely():
    with pytest.raises(AnalysisBudgetExceeded):
        analyze_repository("tests/fixtures", max_work=10)


def test_budget_parameter_mutually_exclusive():
    with pytest.raises(ValueError):
        analyze_repository("tests/fixtures", max_work=1000, budget=AnalysisBudget(1000))
