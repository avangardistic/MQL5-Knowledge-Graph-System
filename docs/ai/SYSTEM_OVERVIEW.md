# SYSTEM OVERVIEW (AI Audience)

**Optimized for AI coding agents.** Explicit, contract-focused. This is the
entry point: read it first, then branch to the referenced docs.

## What this system is

The **MQL5 Knowledge Graph System** (`mql5_kg` package) parses MQL5 source,
builds a canonical, evidence-backed knowledge graph, indexes it
deterministically, and exposes a bounded code-intelligence API. AI agents use
it to reason about MQL5 repositories **structurally** using compact context
packages instead of reading whole source trees — reducing tokens without
sacrificing correctness or evidence.

## Invariants you must never violate

`ARCHITECTURE_INVARIANTS.md`. In one line each:

1. One authoritative `CodeGraph` per analysis.
2. Semantics live in the core, never in adapters.
3. Relationships preserve origin + evidence.
4. Ambiguity stays ambiguous.
5. Deterministic identity + results.
6. No mixing snapshot revisions in one request.
7. MCP/HTTP never expand filesystem access.
8. Context budgets explicit + enforced.
9. Core works without MCP.
10. Reference docs ≠ graph truth.
11. Graphify/LLM overlay stays labeled inference.
12. No graph published from failed analysis.

## Data flow

```
MQL5 source
   │  discover_sources()
   v
lexer → parser → ParseResult (declarations, calls, includes, diagnostics)
   │
   v
resolver (build_graph): includes, scopes, calls, ambiguity
   │
   v
CodeGraph (immutable, deterministic) ── enrich_runtime()
   │
   v
GraphSnapshot.publish() ── validation, no partial graph
   │
   v
GraphIndex ── IntelligenceKernel ── CLI / HTTP / MCP
```

## Core modules

| Module | Role |
|--------|------|
| `lexer.py` | Tokenizes; strings/comments immune to analysis |
| `parser.py` | Tolerant structural parser (declarations, calls, includes) |
| `ir.py` `symbols.py` `scopes.py` | IR, identity, scope models |
| `resolver.py` | Include/call resolution; ambiguity preservation |
| `runtime.py` | Runtime/event relationships, separate from calls |
| `graph.py` | Canonical `CodeGraph` |
| `snapshots.py` | Immutable published graph |
| `index.py` `indexer.py` | GraphIndex + end-to-end analysis |
| `evidence.py` `diagnostics.py` | Provenance + diagnostics |
| `analysis_budget.py` | Deterministic work budget |
| `intelligence/kernel.py` | All query operations |
| `context/engine.py` | Budgeted context packages |
| `adapters/{cli,http,mcp}` | Thin projections over the kernel |
| `reference/` `compiler_evidence.py` | Optional, isolated |
| `compat/` | Legacy surface (`graphify`, `MQL5Parser`) |

## Two audiences' docs

- Agents: everything in `docs/ai/`.
- Humans: `docs/` (same facts, prose-first).

Read next, in order:
1. `GRAPH_SCHEMA.md` — the data model.
2. `INTELLIGENCE_CONTRACT.md` — the query contract.
3. `CONTEXT_ENGINE.md` — token-efficiency.
4. `MCP_TOOLS.md` — the AI-facing surface.
5. `ERROR_MODEL.md`, `SECURITY_MODEL.md` — constraints.