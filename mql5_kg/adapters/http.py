"""HTTP API adapter over the Intelligence Kernel (stdlib only).

Endpoints (all under ``/api/v1``):

- ``GET /api/v1/project``              graph identity + counts
- ``GET /api/v1/symbols?target=..``    resolve a symbol (query)
- ``GET /api/v1/search?q=..``          fuzzy symbol search
- ``GET /api/v1/context?target=..``    bounded context
- ``GET /api/v1/references?target=..`` all references (context, both directions)
- ``GET /api/v1/impact?target=..``     upstream impact
- ``GET /api/v1/trace?source=..&target=..``  directed paths
- ``GET /api/v1/context_package?target=..&units=..``  budgeted context package
- ``GET /api/v1/diagnostics``          graph diagnostics

The adapter contains no graph semantics: every response is a projection of a
kernel result or a machine-readable error envelope.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..graph import CodeGraph
from ..intelligence import IntelligenceError, IntelligenceKernel

CONTRACT_VERSION = "1.0.0"

_BOUNDS_DEFAULTS = {
    "max_depth": 1,
    "max_items": 30,
    "max_paths": 3,
    "max_expansions": 10_000,
    "context_units": 100,
}


class KernelRequestHandler(BaseHTTPRequestHandler):
    """Thread-safe handler bound to one immutable kernel."""

    kernel: IntelligenceKernel

    def log_message(self, format: str, *args: Any) -> None:
        # Keep access logs on stderr; never pollute stdout.
        import sys

        sys.stderr.write("%s - - [%s] %s\n" % (
            self.address_string(),
            self.log_date_time_string(),
            format % args,
        ))

    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        self._send(status, {
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "contract_version": CONTRACT_VERSION,
            }
        })

    def _query(self) -> dict[str, str]:
        parsed = urlparse(self.path)
        return {key: values[0] for key, values in parse_qs(parsed.query).items()}

    def _require(self, query: dict[str, str], name: str) -> str | None:
        value = query.get(name)
        if value is None or not value.strip():
            self._send_error(400, "missing_parameter", f"Missing required parameter {name!r}")
            return None
        return value

    def _int(self, query: dict[str, str], name: str, default: int) -> int:
        value = query.get(name)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def _bounds(self, query: dict[str, str]) -> dict[str, int]:
        return {
            "max_depth": self._int(query, "max_depth", _BOUNDS_DEFAULTS["max_depth"]),
            "max_items": self._int(query, "max_items", _BOUNDS_DEFAULTS["max_items"]),
            "max_paths": self._int(query, "max_paths", _BOUNDS_DEFAULTS["max_paths"]),
            "max_expansions": self._int(query, "max_expansions", _BOUNDS_DEFAULTS["max_expansions"]),
            "context_units": self._int(query, "units", _BOUNDS_DEFAULTS["context_units"]),
        }

    def _execute(self, request: dict[str, Any]) -> None:
        try:
            result = self.kernel.execute(request)
        except IntelligenceError as error:
            self._send_error(400, error.code, error.message, error.to_dict())
            return
        except ValueError as error:
            self._send_error(400, "invalid_request", str(error))
            return
        self._send(200, result.to_dict())

    # ------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = self._query()
        if path == "/api/v1/project":
            identity = self.kernel.graph_identity.to_dict()
            graph = self.kernel.index
            self._send(200, {
                "contract_version": CONTRACT_VERSION,
                "graph_identity": identity,
                "counts": {
                    "nodes": len(graph.nodes),
                    "edges": len(graph.edges),
                    "diagnostics": len(graph.diagnostics),
                },
            })
            return
        if path == "/api/v1/symbols":
            target = self._require(query, "target")
            if target is None:
                return
            self._execute({
                "contract_version": CONTRACT_VERSION,
                "operation": "query",
                "targets": [{"value": target, "kind": query.get("kind")}],
                "direction": "both",
                "bounds": self._bounds(query),
            })
            return
        if path == "/api/v1/search":
            target = self._require(query, "q")
            if target is None:
                return
            bounds = self._bounds(query)
            bounds["max_items"] = self._int(query, "limit", 30)
            self._execute({
                "contract_version": CONTRACT_VERSION,
                "operation": "query",
                "targets": [{"value": target, "kind": None}],
                "direction": "both",
                "bounds": bounds,
            })
            return
        if path == "/api/v1/context":
            target = self._require(query, "target")
            if target is None:
                return
            self._execute({
                "contract_version": CONTRACT_VERSION,
                "operation": "context",
                "targets": [{"value": target, "kind": None}],
                "direction": query.get("direction", "both"),
                "bounds": self._bounds(query),
            })
            return
        if path == "/api/v1/references":
            target = self._require(query, "target")
            if target is None:
                return
            self._execute({
                "contract_version": CONTRACT_VERSION,
                "operation": "context",
                "targets": [{"value": target, "kind": None}],
                "direction": "both",
                "bounds": self._bounds(query),
            })
            return
        if path == "/api/v1/impact":
            target = self._require(query, "target")
            if target is None:
                return
            bounds = self._bounds(query)
            bounds["max_depth"] = self._int(query, "depth", 3)
            self._execute({
                "contract_version": CONTRACT_VERSION,
                "operation": "impact",
                "targets": [{"value": target, "kind": None}],
                "direction": "incoming",
                "bounds": bounds,
            })
            return
        if path == "/api/v1/trace":
            source = self._require(query, "source")
            target = self._require(query, "target")
            if source is None or target is None:
                return
            bounds = self._bounds(query)
            bounds["max_depth"] = self._int(query, "depth", 5)
            self._execute({
                "contract_version": CONTRACT_VERSION,
                "operation": "path",
                "targets": [{"value": source, "kind": None}, {"value": target, "kind": None}],
                "direction": "outgoing",
                "bounds": bounds,
            })
            return
        if path == "/api/v1/context_package":
            target = self._require(query, "target")
            if target is None:
                return
            bounds = self._bounds(query)
            bounds["max_depth"] = self._int(query, "depth", 2)
            self._execute({
                "contract_version": CONTRACT_VERSION,
                "operation": "context_package",
                "targets": [{"value": target, "kind": None}],
                "direction": query.get("direction", "both"),
                "bounds": bounds,
            })
            return
        if path == "/api/v1/diagnostics":
            bounds = self._bounds(query)
            bounds["max_items"] = self._int(query, "limit", 250)
            self._execute({
                "contract_version": CONTRACT_VERSION,
                "operation": "diagnostics",
                "targets": [],
                "direction": "both",
                "bounds": bounds,
            })
            return
        self._send_error(404, "not_found", f"Unknown endpoint {path!r}")

    def do_POST(self) -> None:  # noqa: N802
        self._send_error(405, "method_not_allowed", "Only GET endpoints are supported")


def serve_http(graph: CodeGraph, *, host: str = "127.0.0.1", port: int = 8765, revision: int = 1) -> None:
    """Serve a canonical graph over the local HTTP API (blocking)."""

    server = ThreadingHTTPServer((host, port), KernelRequestHandler)
    server.RequestHandlerClass.kernel = IntelligenceKernel(graph, snapshot_revision=revision)
    import sys

    print(
        f"MQL5 Knowledge Graph HTTP API listening on http://{host}:{port}/api/v1/",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
