# Architecture Comparison — Repository A vs Repository B

This document records the architectural observations from Phase 1 archaeology. It feeds
`capability-matrix.md`, `migration-plan.md`, `target-architecture.md`, and the invariants in
`../ai/ARCHITECTURE_INVARIANTS.md`.

## Repository A — MQL5-Knowledge-Graph-System

### Pipeline (implicit)

```text
MQL5 files
   → find_mql5_files()            (CLI)
   → MQL5Parser.parse_file()      (regex extraction + call heuristic)
   → GraphStorage.save_graph()    (graph.json + GRAPH_REPORT.md)
   → MCPServer                    (queries read graph.json directly)
```

### Strengths

- Simple, zero-dependency design; easy to understand.
- MQL5-specific recognition (event handlers, trading/indicator function sets, DLL imports).
- Reasonable symbol categories for the MQL5 domain (input_variable, event_handler, define…).
- The `graphify` CLI command naming (`build`, `query search|symbol|impact|trace|file|includes`, `serve`)
  is user-friendly and worth keeping as a compatibility surface.

### Flaws (why a rewrite is required)

1. **Regex-only parsing.** Symbols and "function bodies" are located with regexes against
   comment/string-stripped text; braces and parens are not paired. A 5000-char window after a
   function's opening line is treated as its body, so calls can be attributed to the wrong caller
   and call edges leak across function boundaries.
2. **No deterministic identity.** Symbols are keyed by bare name; two files defining `OnTick`
   collide, overloads collide, `enum.member` keys are ad hoc.
3. **No scope model.** Resolution is repository-wide name matching; shadowing, receiver types,
   and qualified names are ignored.
4. **No evidence model.** Edges carry only `source/target/type`; there is no origin, confidence,
   location, or ambiguity.
5. **No include resolution.** `#include` strings are recorded and echoed back; unresolved includes
   are not diagnosed; circular includes are not detected.
6. **No diagnostics.** Parse problems are silent or become `error` dicts.
7. **Ambiguity is destroyed.** `get_symbol_context` picks the first fuzzy match.
8. **MCP is broken.** The SDK v1 decorator-style handler registration no longer works with the
   installed MCP SDK (baseline: 26 errors, 15 failures). Queries re-implement graph semantics
   inside the MCP server (adapter-level logic).
9. **No analysis budget, no atomic publication, no fingerprinting, no snapshot consistency.**

## Repository B — mql5-codegraph

### Pipeline (explicit, budgeted)

```text
discover_sources()
   → tokenize()                        (lexer: precise coordinates, recovery diagnostics)
   → parse_source()                    (structural parser: declarations, calls, includes)
   → build_graph()                     (resolver: includes, calls, ambiguity, external nodes)
   → enrich_runtime()                  (runtime dispatches / may-trigger-event)
   → CodeGraph                         (canonical, schema-versioned, atomic save)
   → GraphIndex                        (immutable sorted indexes)
   → IntelligenceKernel                (versioned contract facade)
   → adapters: CLI, MCP, web, exports
```

### Strengths

- Real tokenizer that never interprets strings/comments as code; emits unterminated-* diagnostics.
- Tolerant structural parser with explicit analysis budget; every stage consumes budget and fails
  safely (`AnalysisBudgetExceeded`), with an O(1) token→function map (fixing the O(n·m) flaw
  documented in `ANALYSIS.md`).
- Canonical `CodeGraph` with deterministic `stable_id()` identities, schema version, and atomic
  file publication (`.tmp` + rename).
- Evidence on every edge: origin (`extracted|resolved|runtime|inferred`), confidence, location.
- Ambiguity preserved: `TargetResolution` with `matched|ambiguous|no_match` status; resolver emits
  `AMBIGUOUS_CALL` diagnostics and attaches every candidate.
- Immutable `GraphIndex` (sorted, deterministic) + `IntelligenceKernel` owning all semantics;
  CLI/MCP/web are thin adapters.
- Context engine with explicit `context_units` budget, deterministic ranking, atomic relationship
  packing, and truthful omission reporting.
- Runtime enrichment separates `runtime_dispatches`/`may_trigger_event` from source `calls`.
- MCP: session-based snapshots, fingerprint/`revision_mismatch` protection, read-only annotations,
  lifecycle logging to stderr only, root containment.
- Reference corpus is a fully validated immutable snapshot subsystem (hash-checked, page/section
  canonical order, authority ranking, citations).
- Compiler-evidence correlation is read-only and never mutates the graph.
- Extensive tests incl. intelligence conformance, MCP wire protocol, reference corpus, budget.

### Weaknesses / decisions for the final repo

- Package/CLI naming (`mql5-codegraph`) differs from the final product identity.
- The React dashboard (`web/`) is out of scope for the final repo (kept as HTTP API only).
- `GraphIndex` lives under `intelligence/`; the final repo hoists it to the `index` layer.
- No explicit `symbols`/`scopes`/`evidence` modules; the final repo adds them as documented
  canonical layers on top of the same machinery.

## Resolution

- **Preserve (thin adapter):** `graphify`/`mql5-kg` console scripts, `mql5_kg.cli.graphify`
  module path, the six legacy MCP tool names, legacy dict-shaped graph output capability.
- **Integrate:** Repository B core pipeline, intelligence kernel, context engine, budget,
  diagnostics, runtime enrichment, compiler evidence, reference corpus, GraphML export.
- **Rewrite:** symbol identity rules, scope model, evidence module, snapshot/atomic publication,
  `mql5kg` CLI surface, HTTP API, MCP tool surface, documentation, test suite.
- **Remove:** regex parser, substring call heuristic, adapter-level graph queries, broken SDK v1
  MCP registration, generated artifacts (`graph.json`, `GRAPH_REPORT.md`, `__pycache__`,
  `mql5_kg.egg-info`) from the working tree.
