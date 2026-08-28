# MCP TOOLS (AI Audience)

The **MCP server** (`mql5_kg/adapters/mcp/server.py`) is a read-only,
kernel-backed stdio server. Read `SECURITY_MODEL.md` before using. Every tool
returns the intelligence contract; errors are machine-readable envelopes.

Start: `mql5kg-mcp` (or `python -m mql5_kg.adapters.mcp.server`).

## Workflow

1. `project_status` — see the active snapshot.
2. `index_project` — load a trusted local root into an in-memory snapshot.
3. Query tools.

## Tools

### project_status
No args. → `{status, revision, root, counts, graph_identity}`.

### index_project(root, include_roots?, excluded?, max_work?)
Read a trusted local MQL5 project into a snapshot. Does not write or persist.
`excluded` are directory **names only** (paths rejected). Reuse if identical.

### search_symbols(query, kind?, max_items?, expected_source_fingerprint?)
Fuzzy symbol search; preserves matched/ambiguous/no_match.

### get_symbol(target, expected_source_fingerprint?)
Resolve one symbol: definition, location, signature.

### get_symbol_context(target, direction?, max_depth?, max_items?, ...)
Bounded context: definition + callers/callees + dependencies + diagnostics.

### find_callers(target, max_depth?, max_items?, ...)
Incoming `calls` edges.

### find_callees(target, max_depth?, max_items?, ...)
Outgoing `calls` edges.

### find_references(target, max_depth?, ...)
Incoming + outgoing context.

### find_dependencies(target, max_depth?, ...)
Outgoing `includes`/`defines` edges.

### get_file_summary(file_path, ...)
Summary of a file node (loc, defined symbols).

### resolve_include(file_path, ...)
Which file includes which target (outgoing `includes`, depth 1).

### resolve_includes(file_path, max_depth?, ...)
Legacy: recursive include chain (bounded).

### impact_analysis(target, max_depth?, max_items?, ...)
Bounded upstream impact.

### trace_execution_flow(source, target, max_depth?, max_paths?, ...)
Directed paths with per-hop evidence.

### get_diagnostics(max_items?, ...)
Ordered graph diagnostics.

### get_context_package(target, direction?, max_depth?, max_expansions?, context_units?, ...)
Deterministic budgeted package for AI review; truthful omissions.

## Reference tools
When a reference corpus is attached (`ReferenceSession`): corpus search /
excerpt tools returning citations (`evidence_class: "reference_document"`),
`expected_corpus_fingerprint` guards freshness. Reference results never become
code-graph truth.

## Contract

All results carry: `graph_identity` (schema version, source fingerprint,
revision), `resolution` status, relationship `evidence` (origin, confidence,
location), `completion`/omissions. Preserve these when relaying claims to a
user. Never present an `ambiguous` resolution as certain.

## Versioning / semantics

- `get_symbol_context` etc. are thin projections — they never implement graph
  logic themselves.
- Tool schemas are versioned with the intelligence contract; changing them
  follows `CHANGE_GUIDE.md`.