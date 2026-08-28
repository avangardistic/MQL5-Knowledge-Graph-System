"""Intelligence Kernel tests: operations, ambiguity, fingerprints, determinism."""

import pytest

from mql5_kg.indexer import analyze_repository
from mql5_kg.intelligence import IntelligenceError, IntelligenceKernel
from mql5_kg.intelligence.models import IntelligenceRequest

from conftest import FIXTURES


@pytest.fixture(scope="module")
def kernel():
    graph = analyze_repository(str(FIXTURES))
    return IntelligenceKernel(graph, snapshot_revision=1)


def test_query_operation(kernel):
    result = kernel.execute({
        "operation": "query",
        "targets": [{"value": "CalculateLotSize", "kind": None}],
        "direction": "both",
    })
    assert result.operation == "query"
    assert result.resolution[0].status == "matched"
    assert result.nodes[0].name == "CalculateLotSize"
    assert result.completion.reason == "complete"


def test_no_match_preserved(kernel):
    result = kernel.execute({
        "operation": "query",
        "targets": [{"value": "NoSuchSymbolXYZ", "kind": None}],
        "direction": "both",
    })
    assert result.resolution[0].status == "no_match"
    assert result.completion.reason == "no_match"


def test_ambiguous_resolution_preserved(kernel):
    result = kernel.execute({
        "operation": "query",
        "targets": [{"value": "OnTick", "kind": None}],
        "direction": "both",
    })
    # Multiple fixtures define OnTick; ambiguity must be preserved, not collapsed.
    assert result.resolution[0].status == "ambiguous"
    assert len(result.resolution[0].candidates) > 1


def test_context_operation(kernel):
    result = kernel.execute({
        "operation": "context",
        "targets": [{"value": "CloseAllPositions", "kind": None}],
        "direction": "both",
        "bounds": {"max_depth": 1, "max_items": 200},
    })
    assert result.nodes
    assert result.relationships


def test_impact_operation(kernel):
    result = kernel.execute({
        "operation": "impact",
        "targets": [{"value": "CloseAllPositions", "kind": None}],
        "direction": "incoming",
        "bounds": {"max_depth": 3, "max_items": 500},
    })
    assert result.completion.search_complete


def test_path_operation(kernel):
    result = kernel.execute({
        "operation": "path",
        "targets": [{"value": "OnTick", "kind": None}, {"value": "CloseAllPositions", "kind": None}],
        "direction": "outgoing",
        "bounds": {"max_depth": 5, "max_paths": 3},
    })
    for path in result.paths:
        assert len(path.node_ids) == len(path.hops) + 1
        for hop in path.hops:
            assert hop.evidence.location is not None


def test_diagnostics_operation(kernel):
    result = kernel.execute({"operation": "diagnostics", "targets": []})
    assert result.diagnostics
    for diagnostic in result.diagnostics:
        assert diagnostic.severity in {"error", "warning", "info"}


def test_context_package_operation(kernel):
    result = kernel.execute({
        "operation": "context_package",
        "targets": [{"value": "CloseAllPositions", "kind": None}],
        "direction": "both",
        "bounds": {"context_units": 50, "max_depth": 2},
    })
    package = result.context_package
    assert package.budget_used <= package.budget_limit


def test_graph_identity(kernel):
    identity = kernel.graph_identity.to_dict()
    assert identity["graph_schema_version"] == "1.0.0"
    assert identity["snapshot_revision"] == 1
    assert identity["source_fingerprint"]


def test_fingerprint_mismatch_rejected(kernel):
    with pytest.raises(IntelligenceError) as exc_info:
        kernel.execute({
            "operation": "query",
            "targets": [{"value": "OnTick", "kind": None}],
            "expected_source_fingerprint": "wrong-fingerprint",
        })
    assert exc_info.value.code == "graph_identity_mismatch"


def test_deterministic_results(kernel):
    request = {
        "operation": "context",
        "targets": [{"value": "CloseAllPositions", "kind": None}],
        "direction": "both",
        "bounds": {"max_depth": 1, "max_items": 200},
    }
    assert kernel.execute(request).to_json() == kernel.execute(request).to_json()


def test_unsupported_operation(kernel):
    # The request model validates operations, so reaching the kernel dispatch
    # with an unknown operation requires bypassing model validation (defensive
    # path). Dict input is validated first and raises invalid_request.
    request = IntelligenceRequest(operation="query", targets=())
    object.__setattr__(request, "operation", "teleport")
    with pytest.raises(IntelligenceError) as exc_info:
        kernel.execute(request)
    assert exc_info.value.code == "unsupported_operation"


def test_unsupported_operation_from_dict_is_invalid_request(kernel):
    with pytest.raises(IntelligenceError) as exc_info:
        kernel.execute({"operation": "teleport", "targets": []})
    assert exc_info.value.code == "invalid_request"


def test_contract_version_negotiation(kernel):
    with pytest.raises(IntelligenceError) as exc_info:
        kernel.execute({
            "contract_version": "2.0.0",
            "operation": "query",
            "targets": [{"value": "x", "kind": None}],
        })
    assert exc_info.value.code == "unsupported_contract_version"


def test_legacy_projectors(kernel):
    nodes = kernel.legacy_find_nodes("CloseAll")
    assert nodes
    neighborhood = kernel.legacy_neighborhood([nodes[0].id], depth=1)
    assert "nodes" in neighborhood and "edges" in neighborhood
