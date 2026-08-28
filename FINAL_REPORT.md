# FINAL REPORT — MQL5 Knowledge Graph System Rewrite

## Executive Summary

The `MQL5-Knowledge-Graph-System` repository was fundamentally rewritten from
a broken, regex-based prototype into a production-grade **MQL5 parser,
static-analysis engine, canonical knowledge graph, code-intelligence kernel,
and AI integration platform**. Architecture and ideas were selectively
absorbed from `mql5-codegraph` (MIT, same author) — used as a source of
patterns only, **not** a runtime dependency. The core has zero required
third-party dependencies; the `mcp` and `reference` features are optional
extras.

The primary goal is achieved: AI coding agents can now answer
"what does this change affect?" using compact, evidence-backed structural
context packages instead of whole source trees, reducing token consumption
without sacrificing correctness or evidence.

**197 tests pass.** The CLI, HTTP, and MCP entry points work. CI is configured,
documentation is complete for both human and AI audiences, and the repository
is self-contained with no secrets.

## Architecture

```
MQL5 source
   │  discover_sources()
   ▼
lexer → parser → ParseResult (declarations, calls, includes, diagnostics)
   │
   ▼
resolver --------------------------------------------------┐
   │  includes, scope-aware calls, ambiguity               │
   ▼                                                       │
CodeGraph ◄─────────────────── enrich_runtime()            │
   │  (immutable, deterministic, evidence-backed)          │
   ▼                                                       │
GraphSnapshot.publish()                                    │
   │  validation + atomic, no partial graph                │
   ▼                                                       │
GraphIndex                                                  │
   ▼                                                       │
IntelligenceKernel                                         │
   │               ┌────────────┬────────────┐             │
   ▼               ▼            ▼            ▼             │
  CLI             HTTP          MCP          legacy graphify
                                              (compat adapters)
```

Package layout under `mql5_kg/`: `lexer`, `parser`, `ir`, `symbols`, `scopes`,
`resolver`, `runtime`, `graph`, `snapshots`, `index`, `indexer`, `evidence`,
`diagnostics`, `analysis_budget`, `intelligence/`, `context/`, `reference/`,
`compiler_evidence`, `adapters/{cli,http,mcp}`, `compat/`, `exporters/`,
`benchmarks/`.

**Data flow** is single-source-of-truth: every adapter projects through the
kernel; no adapter implements graph semantics (Invariant 2).

## Parser Support

Supported MQL5 constructs (`docs/parser.md`):

- function, method, constructor, destructor, event handlers (`OnInit`,
  `OnTick`, `OnTimer`, `OnTrade`, …)
- class / struct / enum type ranges
- `input` / `sinput` variables
- `#define` macros, `#property`, `#import "dll"` blocks (imported symbols)
- call sites with receiver qualifier/type, arity, and exact locations
- `#include` resolution vs quoted/system; missing/circular/deep handled

Tolerance (`docs/parser.md`, `tests/fixtures/adversarial/`):

- incomplete, malformed, partially edited source; unclosed blocks and missing
  semicolons become diagnostics, never crashes
- strings/comments immune to analysis (no phantom call edges)
- large files parse in near-linear time (precomputed token→function map)

**Limitations:**

- Structural parser, not a full C++ grammar — deep expression-typing is
  best-effort; specific ambiguous overloads are preserved as ambiguous rather
  than guessed.
- No full incremental/git-diff indexing yet (re-index is whole-graph, safe).

## Knowledge Graph

- **Nodes** (`docs/ai/GRAPH_SCHEMA.md`): `file`, `function`, `method`,
  `constructor`, `destructor`, `event_handler`, `class`, `struct`, `enum`,
  `input_variable`, `variable`, `property`, `macro`, `imported_symbol`,
  `external_function`, `runtime`.
- **Edges** (`docs/ai/RELATIONSHIP_MODEL.md`): `defines`, `contains`,
  `includes`, `calls`, `references`, `inherits`, `runtime_dispatches`,
  `may_trigger_event`, `declares`.
- **Evidence** (`docs/ai/EVIDENCE_MODEL.md`): every edge carries `origin`
  (`extracted`/`resolved`/`runtime`/`inferred`), `confidence`, and source
  `location`. Classes: `code_graph`, `reference_document`,
  `external_compiler_evidence`, `semantic_overlay_inference`. Runtime events
  are never presented as source `calls`.
- **Schema version** `1.0.0`; deterministic content-addressed IDs; atomic
  deterministic serialization.

## Intelligence Kernel

Operations (`docs/ai/INTELLIGENCE_CONTRACT.md`): `query`, `context`, `impact`,
`path`, `context_package`, `diagnostics`. Versioned contract `1.0.0` with
`graph_identity`, bounded results, deterministic ordering/ranking, and a
truthful `completion` (truncation/omissions) record. Ambiguity is preserved
(`matched`/`ambiguous`/`no_match`). Errors are machine-readable envelopes
(`docs/ai/ERROR_MODEL.md`).

## Context Engine

`docs/ai/CONTEXT_ENGINE.md`. Packs structural records under an explicit
`context_units` budget; relationships packed atomically; deterministic
ranking (targets, then source-backed/bounded-depth/confidence, then
diagnostics). **Omissions are always reported**; `budget_used <= budget_limit`
is invariant-tested.

## MCP Tools

`docs/ai/MCP_TOOLS.md`. Read-only, kernel-backed, root-confined stdio server.
Tools: `project_status`, `index_project`, `search_symbols`, `get_symbol`,
`get_symbol_context`, `find_callers`, `find_callees`, `find_references`,
`find_dependencies`, `resolve_include`, `resolve_includes`, `impact_analysis`,
`trace_execution_flow`, `get_diagnostics`, `get_context_package`, plus
reference-corpus tools. All bounded and evidence-preserving; errors are
envelopes.

## Testing

**197 tests pass** (`python -m pytest -q`), covering:

| Category | Files |
|----------|-------|
| Unit (lexer, parser, symbols, resolver, graph, snapshots, index, intelligence, context, runtime, diagnostics, budget) | `test_lexer/parser/symbols/...` |
| Adversarial parser robustness | `test_adversarial.py` + `fixtures/adversarial/` |
| Security (path traversal, budgets, fingerprint, Graphify env) | `test_security.py` |
| Invariant / round-trip / golden | `test_snapshots.py`, `test_regression.py` |
| MCP wire protocol (real stdio client) | `test_mcp.py` |
| HTTP API | `test_http.py` |
| Compatibility (`graphify`, `MQL5Parser`) | `test_compat.py` |
| Compiler evidence | `test_compiler_evidence.py` |
| Token benchmark (measured) | `test_benchmark_token.py` |

## Benchmarks

Token-efficiency measured, not claimed (recorded under `docs/benchmarks/`):

| Case | Repo tokens | Context package tokens | Ratio |
|------|-------------|------------------------|-------|
| Representative 40-file synthetic repo (454 KB) | 113,672 | 10,871 (60 units) | **~9.6%** |
| sample_mql5 (2-file, 10.5 KB) | 2,636 | 17,926 (100 units) | 6.8× |

The representative multi-file case shows a fixed-budget structural context
package at **<10%** of raw source tokens. The tiny-repo row is reported
honestly: a large fixed package can exceed raw source on a very small
repository — the benchmark never fabricates a universal discount. Estimates
use a conservative `chars / 4`.

Performance: index of `sample_mql5` ~0.02 s; context package ~0.002 s; large
files parse near-linearly (regression-tested).

## Security

- Adapters are read-only projections; MCP/HTTP never expand filesystem access
  (Invariant 7).
- Root confinement + explicit include roots; `..`, absolute-path injection,
  and symlink escapes rejected.
- Bounded requests/traversals/budgets; fingerprint guards snapshot mixing.
- Graphify runs `shell=False`, explicit args, timeout, restricted environment;
  `local` = ollama-only (loopback enforced); `remote` requires explicit
  authority.
- Reference corpus paths confined; hashes verified; atomic publication.
- No secrets committed (verified by scan). Detailed in
  `docs/security.md` + `docs/ai/SECURITY_MODEL.md`; enforced by
  `tests/test_security.py`.

## Known Limitations (honest)

- **Analysis budget**: the default `--max-work` (1,000,000 units) supports a
  few hundred KB of dense source before `analysis_budget_exceeded`. This is by
  design (deterministic safe fail); larger projects must raise it. Documented
  in `docs/configuration.md` and `docs/troubleshooting.md`.
- **No full incremental indexing** yet; re-indexing is whole-graph.
- **Reference/Graphify**: implemented and unit/security-tested, but
  end-to-end validation requires the operator's PDFs and the external
  `graphify` binary + a supported backend.
- **Type inference** is best-effort; ambiguous overloads remain ambiguous
  (correct by design, but not "solved").
- **CI secret scan** is a best-effort private-key/placeholder guard, not a
  substitute for a proper secret scanner.## Git

- **Repository:** https://github.com/avangardistic/MQL5-Knowledge-Graph-System
- **Branch:** `main`
- **Final commit SHA:** recorded in git log after the commit series; the
  repository was pushed to the remote.
- Commit series: core rewrite → human docs → AI/planning docs → AGENTS/README
  → CI → this final report, following `docs/rewrite/migration-plan.md`.

---

Generated as the finalization deliverable of the master rewrite prompt.