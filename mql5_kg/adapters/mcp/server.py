"""Official-SDK MCP stdio projection for the MQL5 Knowledge Graph.

The server is a thin, read-only adapter over kernel-backed sessions. It never
implements graph semantics, never expands filesystem access beyond the
operator-selected project root, and keeps lifecycle logging on stderr only so
the stdio protocol stays clean (Invariants 2, 7, 9).
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import json
import os
import sys
from typing import Any

from .service import AdapterError, ProjectSession, ReferenceSession

SERVER_NAME = "mql5-knowledge-graph"
LIFECYCLE_PREFIX = "mql5-kg-mcp.lifecycle "
SERVER_INSTRUCTIONS = (
    "Local, read-only MQL5 project intelligence. Call project_status first. "
    "Call index_project only for a trusted absolute local project root, then "
    "use bounded intelligence tools. Preserve ambiguity, evidence, origin, "
    "completion, truncation, and graph fingerprint in every claim. Re-index "
    "after source changes. This server never edits source, writes indexes, "
    "invokes external tools, or accesses the network."
)

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.exceptions import ToolError
    from mcp.types import ToolAnnotations

    MCP_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the optional extra
    MCP_AVAILABLE = False
    FastMCP = None  # type: ignore[assignment]
    ToolError = None  # type: ignore[assignment]
    ToolAnnotations = None  # type: ignore[assignment]

READ_ONLY_ANNOTATIONS = (
    ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
    if MCP_AVAILABLE
    else None
)


def _distribution_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "source"
    except Exception:
        return "unknown"


def _emit_lifecycle(event: str, **details: object) -> None:
    payload = {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": event,
        "server": SERVER_NAME,
        "transport": "stdio",
        "pid": os.getpid(),
        "parent_pid": os.getppid(),
        "package_version": _distribution_version("mql5-kg"),
        "python_version": (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
        **details,
    }
    try:
        sys.stderr.write(
            LIFECYCLE_PREFIX
            + json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
        sys.stderr.flush()
    except (OSError, ValueError):
        # Telemetry must never become a new failure mode for the MCP transport.
        pass


def _call(method, /, *args, **kwargs) -> dict[str, Any]:
    try:
        return method(*args, **kwargs)
    except AdapterError as error:
        if ToolError is None:  # pragma: no cover
            raise
        raise ToolError(error.to_json()) from error


def create_server(
    session: ProjectSession | None = None,
    reference_session: ReferenceSession | None = None,
) -> Any:
    """Create one MCP server bound to independent project/reference sessions."""

    if not MCP_AVAILABLE:  # pragma: no cover
        raise RuntimeError("MCP server requires the optional 'mcp' dependency: pip install 'mql5-kg[mcp]'")

    project = session or ProjectSession()
    references = reference_session or ReferenceSession()
    server = FastMCP(
        SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
        log_level="ERROR",
    )

    @server.tool(
        name="project_status",
        description=(
            "Report the active in-memory MQL5 project snapshot without scanning "
            "or changing the filesystem."
        ),
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def project_status() -> dict[str, Any]:
        return _call(project.project_status)

    @server.tool(
        name="index_project",
        description=(
            "Read a trusted local MQL5 project into an in-memory graph snapshot. "
            "This does not modify source or persist an index. If "
            "analysis_budget_exceeded is returned, narrow root/include_roots "
            "before increasing max_work."
        ),
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def index_project(
        root: str,
        include_roots: list[str] | None = None,
        excluded: list[str] | None = None,
        max_work: int | None = None,
    ) -> dict[str, Any]:
        return _call(
            project.index_project,
            root,
            include_roots or (),
            excluded or (),
            max_work=max_work,
        )

    @server.tool(
        name="search_symbols",
        description=(
            "Search symbols by name, qualified name, or partial match while "
            "preserving exact, ambiguous, and no-match status."
        ),
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def search_symbols(
        query: str,
        kind: str | None = None,
        max_items: int = 30,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return _call(
            project.query_symbols,
            query,
            kind=kind,
            max_items=max_items,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    @server.tool(
        name="get_symbol",
        description="Resolve a single symbol (definition, location, signature).",
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def get_symbol(
        target: str,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return _call(project.query_symbols, target, expected_source_fingerprint=expected_source_fingerprint)

    @server.tool(
        name="get_symbol_context",
        description=(
            "Return the bounded relationship context of a symbol: definition, "
            "callers, callees, dependencies, and diagnostics with evidence."
        ),
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def get_symbol_context(
        target: str,
        direction: str = "both",
        max_depth: int = 1,
        max_items: int = 900,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return _call(
            project.get_context,
            target,
            direction=direction,
            max_depth=max_depth,
            max_items=max_items,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    @server.tool(
        name="find_callers",
        description="Return the symbols that call a given symbol.",
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def find_callers(
        target: str,
        max_depth: int = 1,
        max_items: int = 200,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return _call(
            project.get_context,
            target,
            direction="incoming",
            relationship_types=["calls"],
            max_depth=max_depth,
            max_items=max_items,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    @server.tool(
        name="find_callees",
        description="Return the symbols a given symbol calls.",
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def find_callees(
        target: str,
        max_depth: int = 1,
        max_items: int = 200,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return _call(
            project.get_context,
            target,
            direction="outgoing",
            relationship_types=["calls"],
            max_depth=max_depth,
            max_items=max_items,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    @server.tool(
        name="find_references",
        description="Return all references to a symbol (incoming and outgoing).",
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def find_references(
        target: str,
        max_depth: int = 1,
        max_items: int = 900,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return _call(
            project.get_context,
            target,
            direction="both",
            max_depth=max_depth,
            max_items=max_items,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    @server.tool(
        name="find_dependencies",
        description="Return the file/symbol dependencies of a symbol (includes, defines).",
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def find_dependencies(
        target: str,
        max_depth: int = 1,
        max_items: int = 300,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return _call(
            project.get_context,
            target,
            direction="outgoing",
            relationship_types=["includes", "defines"],
            max_depth=max_depth,
            max_items=max_items,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    @server.tool(
        name="get_file_summary",
        description="Summarize a file: location, line count, and defined symbols.",
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def get_file_summary(
        file_path: str,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return _call(
            project.query_symbols,
            file_path,
            kind="file",
            max_items=1,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    @server.tool(
        name="resolve_include",
        description="Resolve one include edge: which file includes which target.",
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def resolve_include(
        file_path: str,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return _call(
            project.get_context,
            file_path,
            direction="outgoing",
            relationship_types=["includes"],
            max_depth=1,
            max_items=100,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    @server.tool(
        name="resolve_includes",
        description=(
            "Legacy compatibility tool: recursively resolve the include chain "
            "for a file (bounded by max_depth)."
        ),
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def resolve_includes(
        file_path: str,
        max_depth: int = 3,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return _call(
            project.get_context,
            file_path,
            direction="outgoing",
            relationship_types=["includes"],
            max_depth=max_depth,
            max_items=200,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    @server.tool(
        name="impact_analysis",
        description="Return bounded upstream impact of changing a symbol.",
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def impact_analysis(
        target: str,
        max_depth: int = 3,
        max_items: int = 2000,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return _call(
            project.get_impact,
            target,
            max_depth=max_depth,
            max_items=max_items,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    @server.tool(
        name="trace_execution_flow",
        description="Find bounded directed paths between two symbols with evidence per hop.",
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def trace_execution_flow(
        source: str,
        target: str,
        max_depth: int = 5,
        max_paths: int = 3,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return _call(
            project.find_paths,
            source,
            target,
            max_depth=max_depth,
            max_paths=max_paths,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    @server.tool(
        name="get_diagnostics",
        description="Return bounded graph diagnostics from the active project snapshot.",
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def get_diagnostics(
        max_items: int = 250,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return _call(
            project.get_diagnostics,
            max_items=max_items,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    @server.tool(
        name="get_context_package",
        description=(
            "Build a deterministic bounded context package for AI review while "
            "preserving evidence, ambiguity, and omission reasons."
        ),
        annotations=READ_ONLY_ANNOTATIONS,
        structured_output=True,
    )
    def get_context_package(
        target: str,
        direction: str = "both",
        max_depth: int = 2,
        max_expansions: int = 10_000,
        context_units: int = 100,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return _call(
            project.get_context_package,
            target,
            direction=direction,
            max_depth=max_depth,
            max_expansions=max_expansions,
            context_units=context_units,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    return server


def main() -> None:
    """Run the bundled local server over MCP stdio."""

    _emit_lifecycle("starting")
    try:
        create_server().run(transport="stdio")
    except KeyboardInterrupt:
        _emit_lifecycle(
            "stopped",
            reason="keyboard_interrupt",
            exit_code=130,
        )
        raise
    except SystemExit as error:
        exit_code = error.code if isinstance(error.code, int) else 1
        _emit_lifecycle(
            "stopped" if exit_code == 0 else "crashed",
            reason="system_exit",
            exit_code=exit_code,
        )
        raise
    except BaseException as error:
        _emit_lifecycle(
            "crashed",
            reason="unhandled_exception",
            exception_type=type(error).__name__,
            exit_code=1,
        )
        raise
    else:
        _emit_lifecycle(
            "stopped",
            reason="stdio_eof",
            exit_code=0,
        )


if __name__ == "__main__":
    main()
