"""HTTP API adapter tests."""

import json
import threading
from urllib.request import urlopen, Request
from urllib.error import HTTPError

import pytest

from mql5_kg.graph import CodeGraph
from mql5_kg.indexer import analyze_repository
from mql5_kg.adapters.http import KernelRequestHandler, serve_http

from conftest import FIXTURES


@pytest.fixture(scope="module")
def http_server():
    graph = analyze_repository(str(FIXTURES))
    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), KernelRequestHandler)
    server.RequestHandlerClass.kernel = __import__(
        "mql5_kg.intelligence", fromlist=["IntelligenceKernel"]
    ).IntelligenceKernel(graph, snapshot_revision=1)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base
    server.shutdown()
    server.server_close()


def get(base: str, path: str):
    with urlopen(base + path, timeout=10) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_project_endpoint(http_server):
    status, payload = get(http_server, "/api/v1/project")
    assert status == 200
    assert payload["graph_identity"]["graph_schema_version"] == "1.0.0"
    assert payload["counts"]["nodes"] > 0


def test_symbols_endpoint(http_server):
    status, payload = get(http_server, "/api/v1/symbols?target=CalculateLotSize")
    assert status == 200
    assert payload["resolution"][0]["status"] == "matched"


def test_search_endpoint(http_server):
    status, payload = get(http_server, "/api/v1/search?q=OnTick")
    assert status == 200
    assert payload["operation"] == "query"


def test_context_endpoint(http_server):
    status, payload = get(http_server, "/api/v1/context?target=CloseAllPositions")
    assert status == 200
    assert payload["operation"] == "context"


def test_impact_endpoint(http_server):
    status, payload = get(http_server, "/api/v1/impact?target=CloseAllPositions")
    assert status == 200
    assert payload["operation"] == "impact"


def test_trace_endpoint(http_server):
    status, payload = get(
        http_server, "/api/v1/trace?source=OnTick&target=CloseAllPositions"
    )
    assert status == 200
    assert payload["operation"] == "path"


def test_context_package_endpoint(http_server):
    status, payload = get(
        http_server, "/api/v1/context_package?target=OnTick&units=30"
    )
    assert status == 200
    package = payload["context_package"]
    assert package["budget_used"] <= package["budget_limit"]


def test_diagnostics_endpoint(http_server):
    status, payload = get(http_server, "/api/v1/diagnostics")
    assert status == 200
    assert payload["operation"] == "diagnostics"


def test_missing_parameter_rejected(http_server):
    with pytest.raises(HTTPError) as exc_info:
        get(http_server, "/api/v1/symbols")
    assert exc_info.value.code == 400


def test_unknown_endpoint_404(http_server):
    with pytest.raises(HTTPError) as exc_info:
        get(http_server, "/api/v1/nope")
    assert exc_info.value.code == 404


def test_post_rejected(http_server):
    request = Request(http_server + "/api/v1/project", data=b"{}", method="POST")
    with pytest.raises(HTTPError) as exc_info:
        with urlopen(request, timeout=10):
            pass
    assert exc_info.value.code == 405
