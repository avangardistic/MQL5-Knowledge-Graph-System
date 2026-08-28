# MQL5 Knowledge Graph System

[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A production-grade **MQL5 parser, static-analysis engine, canonical knowledge
graph, code-intelligence engine, and AI integration platform** for MQL5
codebases. It lets AI coding agents understand MQL5 repositories structurally
and relationally while dramatically reducing the source context — and therefore
the token consumption — required for a task.

```
Developer edits MQL5 code
        │
        ▼
 MQL5 Knowledge Graph
        │
        ▼
 Intelligence Kernel
        │
        ▼
 CLI / HTTP / MCP
        │
        ▼
     AI Coding Agent
        │
        ▼
 "What does this change affect?"
        │
        ▼
 Compact structural context + targeted source
```

## What it is

A single, coherent system that combines:

- a **tolerant MQL5 lexer and structural parser** (comments, strings, macros,
  `#import` blocks, event handlers, classes, overloads, broken source);
- a **canonical knowledge graph** with typed, evidence-backed relationships
  (`calls`, `includes`, `defines`, `references`, `inherits`, `runtime_dispatches`,
  …) and source locations;
- a **deterministic Intelligence Kernel** (symbol search, callers/callees,
  impact analysis, execution tracing, diagnostics, context packages);
- a **context engine** that packs structural records under an explicit unit
  budget and truthfully reports omissions;
- **adapters**: a `mql5kg` CLI, an HTTP API, an MCP server, and legacy
  compatibility entry points — all projections over the same kernel;
- **optional isolated subsystems**: a reference corpus (MQL5 docs/PDFs) and a
  Graphify semantic overlay that can never become graph truth;
- **sound incremental indexing** (`--incremental`): unchanged files skip
  re-parsing via a persisted content-hash cache while repository-wide
  resolution always runs, so results equal a full rebuild.

Ambiguity is preserved (never invented away). Evidence is preserved on every
relationship (never silently upgraded). Analysis is deterministic (same source
+ same configuration ⇒ same graph identity). Failed analysis never replaces the
last valid snapshot.

## Installation

```bash
pip install -e .            # core (stdlib only)
pip install -e ".[mcp]"     # + MCP server
pip install -e ".[dev]"     # + test dependencies
```

Requires Python 3.10+.

## Quick start

```bash
# Index a project into a canonical graph
mql5kg index ./path/to/MQL5/Experts -o graph.json

# Incremental re-index (reuses parsed unchanged files)
mql5kg index ./path/to/MQL5/Experts --incremental -o graph.json

# Query
mql5kg search graph.json "position"
mql5kg symbol graph.json ClosePosition
mql5kg callers graph.json ClosePosition
mql5kg callees graph.json OnTick
mql5kg impact graph.json CalculateRisk
mql5kg trace graph.json OnTick OrderSend
mql5kg context graph.json OnTick --budget 60
mql5kg diagnostics graph.json
mql5kg export graph.json --format graphml -o graph.graphml

# Machine-readable JSON everywhere
mql5kg impact graph.json CalculateRisk --json

# HTTP API
mql5kg serve --graph graph.json --port 8765
```

### MCP

```bash
mql5kg-mcp          # stdio MCP server (or: python -m mql5_kg.adapters.mcp.server)
```

Configure the server in your MCP client with command `mql5kg-mcp` (or
`python -m mql5_kg.adapters.mcp.server`). The server exposes
`project_status`, `index_project`, `search_symbols`, `get_symbol`,
`get_symbol_context`, `find_callers`, `find_callees`, `find_references`,
`find_dependencies`, `resolve_include`, `impact_analysis`,
`trace_execution_flow`, `get_diagnostics`, and `get_context_package` — all
read-only, bounded, and confined to the operator-selected project root.

Legacy commands still work unchanged:

```bash
python -m mql5_kg.cli.graphify build .
python -m mql5_kg.cli.graphify query symbol OnTick
python -m mql5_kg.cli.graphify query impact ClosePosition
python -m mql5_kg.cli.graphify query trace OnTick OrderSend
python -m mql5_kg.cli.graphify serve
```

## Example

`mql5kg context graph.json CloseBasket --budget 60` produces a compact package:

```
matched 'CloseBasket'
context budget 60/60
omitted relationships: 3
omitted search_space: None
```

`--json` returns the full machine-readable contract with node summaries,
relationship evidence (origin, confidence, location), and truthful omission
reasons.

## Documentation

| Audience | Where |
|----------|-------|
| Human developers | `docs/` — architecture, parser, graph, intelligence, context engine, CLI, MCP, reference corpus, Graphify, configuration, security, testing, benchmarking, troubleshooting |
| AI coding agents | `docs/ai/` — contracts, invariants, graph/symbol/relationship/evidence/resolution models, MCP tools, error and security models, extension and change guides |
| Future agents | `AGENTS.md` |

Key invariants (see `docs/ai/ARCHITECTURE_INVARIANTS.md`):

1. One authoritative `CodeGraph` per analysis.
2. Graph semantics live in the core, never in adapters.
3. Relationships preserve origin and evidence.
4. Ambiguity stays ambiguous.
5. Deterministic graph identity and query results.
6. One request never mixes graph revisions.
7. MCP/HTTP never expand filesystem access.
8. Context budgets are explicit and enforced.
9. Removing MCP never breaks the parser or kernel.
10. Reference knowledge never silently becomes graph truth.
11. Semantic overlay inference stays labeled as inference.
12. Failed analysis never replaces the last valid graph.

## Architecture

```
src layout (package: mql5_kg/)
├── lexer/parser/ir        # tolerant MQL5 front-end
├── symbols/scopes         # canonical symbol + scope models
├── resolver               # includes, scopes, calls, ambiguity
├── runtime                # runtime/event relationships (separate from calls)
├── evidence/diagnostics   # provenance vocabulary + machine-readable diagnostics
├── graph                  # canonical CodeGraph, validation, snapshots
├── index/incremental      # deterministic GraphIndex + incremental parser cache
├── intelligence/          # Intelligence Kernel + contract models
├── context/               # budgeted context engine
├── reference/             # optional reference corpus (isolated)
├── compiler_evidence.py   # optional external compiler log correlation
├── benchmarks/            # token-efficiency benchmark
├── exporters/             # graphml / markdown / json
└── adapters/              # cli, http, mcp (thin projections)
```

Every adapter calls the Intelligence Kernel; no adapter implements graph
semantics. `mql5-codegraph` is not a runtime dependency — it was used only as a
source of architecture and patterns (see `THIRD_PARTY_NOTICES.md`).

## Development

```bash
python -m pytest            # full suite (unit, adversarial, security, invariants)
python -m mql5_kg.benchmarks.token_efficiency sample_mql5 --symbol OnTick
```

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

For development assistance only. Always test MQL5 code in demo environments
before live deployment. Trading involves substantial risk.
