# MCP Server

The MCP server (`mql5_kg/adapters/mcp/`) exposes the Intelligence Kernel to AI
assistants over the Model Context Protocol (stdio). It is a thin, read-only
projection: it never implements graph semantics, never writes to disk, never
invokes external tools, and never expands filesystem access beyond the
operator-selected project root.

## Start

```bash
mql5kg-mcp                                    # installed entry point
python -m mql5_kg.adapters.mcp.server         # equivalent
```

Requires the optional dependency: `pip install -e ".[mcp]"`.

## Tools

| Tool | Purpose |
|------|---------|
| `project_status` | Report the active in-memory snapshot (revision, counts) |
| `index_project` | Read a trusted local MQL5 project into an in-memory graph snapshot |
| `search_symbols` | Search symbols by name/qualified name (fuzzy) |
| `get_symbol` | Resolve one symbol (definition, location, signature) |
| `get_symbol_context` | Bounded context: definition, callers, callees, dependencies, diagnostics |
| `find_callers` | Who calls this symbol? |
| `find_callees` | What does this symbol call? |
| `find_references` | All references to a symbol |
| `find_dependencies` | File/symbol dependencies (includes, defines) |
| `get_file_summary` | File location, line count, defined symbols |
| `resolve_include` | Which file includes which target |
| `resolve_includes` | Legacy: recursive include chain (bounded) |
| `impact_analysis` | Bounded upstream impact of a change |
| `trace_execution_flow` | Directed paths between two symbols with evidence |
| `get_diagnostics` | Ordered graph diagnostics |
| `get_context_package` | Budgeted context package for AI review |

Every tool:

- has a strict input schema (typed, validated)
- returns the versioned intelligence contract
- is bounded (`max_items`, `max_depth`, `max_expansions`, `context_units`)
- reports ambiguity, evidence origin/confidence, truncation, and omissions
  truthfully
- returns machine-readable error envelopes, never stack traces

## Sessions & snapshots

Each server owns one `ProjectSession` (and an independent `ReferenceSession`
for the reference corpus tools). Indexing publishes a validated snapshot
atomically; a failed analysis leaves the previous snapshot active. Re-indexing
identical source reuses the snapshot (`"reused": true`).

## Security model

- Filesystem access is limited to the root passed to `index_project` plus
  explicit `include_roots`; `excluded` names prune discovery.
- Paths are resolved and confined to the project root; `..` escapes and
  absolute-path injection are rejected.
- No tool reads arbitrary files, follows symlinks outside the root, or
  accepts path traversal.
- Requests are bounded; graph traversal is bounded; budgets are enforced.
- `expected_source_fingerprint` guards against mixing snapshots:
  a mismatch returns `revision_mismatch`-style errors instead of stale data.

See `docs/ai/SECURITY_MODEL.md` for the full threat model and the security
test suite (`tests/test_security.py`).

## Snapshot consistency

Every response carries `graph_identity` with `source_fingerprint` and
`snapshot_revision`, so a client can detect and report stale reads instead of
silently mixing revisions (Invariant 6).

## Reference tools

When a reference corpus is attached (`ReferenceSession`), the MCP surface
gains reference search/excerpt tools that return citations. Reference content
never creates code-graph relationships (Invariant 10).
