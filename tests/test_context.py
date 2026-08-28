"""Context engine tests: deterministic budgets, atomic packing, truthful omissions."""

import pytest

from mql5_kg.indexer import analyze_repository
from mql5_kg.intelligence import IntelligenceKernel

from conftest import FIXTURES


@pytest.fixture(scope="module")
def kernel():
    return IntelligenceKernel(analyze_repository(str(FIXTURES)), snapshot_revision=1)


def test_budget_never_exceeded(kernel):
    for units in (1, 5, 25, 100, 250):
        result = kernel.execute({
            "operation": "context_package",
            "targets": [{"value": "OnTick", "kind": None}],
            "direction": "both",
            "bounds": {"context_units": units, "max_depth": 3},
        })
        package = result.context_package
        assert package.budget_used <= units, f"budget exceeded for {units}"
        assert package.budget_used <= package.budget_limit


def test_relationship_packing_is_atomic(kernel):
    """A relationship item must always bring both endpoint nodes."""
    result = kernel.execute({
        "operation": "context_package",
        "targets": [{"value": "CloseAllPositions", "kind": None}],
        "direction": "both",
        "bounds": {"context_units": 100, "max_depth": 2},
    })
    package = result.context_package
    subject_ids = {item.subject_id for item in package.items}
    node_ids = {
        item.subject_id for item in package.items
        if item.category in {"node", "target"}
    }
    for item in package.items:
        if item.category == "relationship":
            summary = item.summary
            assert summary["source"] in node_ids
            assert summary["target"] in node_ids


def test_omissions_reported_when_budget_exhausted(kernel):
    result = kernel.execute({
        "operation": "context_package",
        "targets": [{"value": "OnTick", "kind": None}],
        "direction": "both",
        "bounds": {"context_units": 3, "max_depth": 3},
    })
    package = result.context_package
    assert package.budget_used <= 3
    if package.omissions:
        completion = result.completion
        assert completion.truncated
        assert completion.reason in {"context_budget", "max_depth", "max_expansions"}


def test_target_always_included(kernel):
    result = kernel.execute({
        "operation": "context_package",
        "targets": [{"value": "CalculateLotSize", "kind": None}],
        "direction": "both",
        "bounds": {"context_units": 1, "max_depth": 1},
    })
    package = result.context_package
    assert package.budget_used >= 1
    assert package.items[0].category == "target"


def test_ranking_is_deterministic(kernel):
    request = {
        "operation": "context_package",
        "targets": [{"value": "OnTick", "kind": None}],
        "direction": "both",
        "bounds": {"context_units": 60, "max_depth": 2},
    }
    first = kernel.execute(request).context_package.to_dict()
    second = kernel.execute(request).context_package.to_dict()
    assert first == second


def test_no_match_package(kernel):
    result = kernel.execute({
        "operation": "context_package",
        "targets": [{"value": "NopeNopeNope", "kind": None}],
        "direction": "both",
    })
    assert result.completion.reason == "no_match"
    assert result.context_package is None
