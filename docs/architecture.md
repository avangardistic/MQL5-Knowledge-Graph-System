# Architecture

The MQL5 Knowledge Graph System converts an MQL5 source tree into a canonical, evidence-backed
knowledge graph and exposes it to AI coding agents through a versioned intelligence kernel.

## Pipeline

```text
source tree → discovery → lexer → parser → resolver (includes+calls+scopes)
            → runtime enrichment → CodeGraph → snapshot validation → GraphIndex
            → IntelligenceKernel → CLI / HTTP / MCP
```

Every stage accounts its work against a deterministic `AnalysisBudget`. If the budget is
exhausted the analysis fails safely with an explicit diagnostic and the previous valid snapshot
remains available — a partial graph is never published.

## Layers

### 1. Lexer (`mql5_kg/lexer.py`)
A recovery-oriented tokenizer. Produces tokens with `line`, `column`, and byte `offset`.
Distinguishes comments, strings, identifiers, keywords-as-identifiers, numbers, operators, and
preprocessor directives. Unterminated strings/comments produce `LEX001`/`LEX002` diagnostics
instead of corrupting the token stream, so code inside strings or comments can never create
relationships.

### 2. Parser (`mql5_kg/parser.py` + `mql5_kg/ir.py`)
A tolerant structural parser. Pairs parentheses and braces (reporting `PARSE001` on unmatched
delimiters), detects type ranges (class/struct/enum), extracts function/method/event-handler
declarations with exact body ranges, parameters, argument counts, call sites, and `#include`
references. It tolerates incomplete, malformed, and partially edited source and emits
diagnostics rather than crashing. An O(1) token→function map keeps large-file parsing linear
instead of quadratic.

### 3. Symbols and scopes (`mql5_kg/symbols.py`, `mql5_kg/scopes.py`)
Symbols carry a kind (file, class, struct, enum, function, method, constructor, destructor,
variable, constant, parameter, property, event_handler, macro, imported_symbol, external_function,
runtime, unknown) and a deterministic identity. Identity is derived from semantic content —
`symbol:<kind>:<file>:<qualified-name>:<signature>` — not from line numbers. The scope model
(global/class/function/block/parameter) drives resolution preference so the resolver avoids
naive repository-wide name matching.

### 4. Resolver (`mql5_kg/resolver.py`)
Resolves `#include` references (relative, system, configured include roots, traversal guards,
unresolved include diagnostics) and call sites. Calls resolve by receiver type, scope, qualified
name, and arity. Resolution states are preserved: `resolved`, `ambiguous` (every candidate kept),
`unresolved` (external/unknown). External MQL5 built-ins become `external_function` nodes.

### 5. Runtime enrichment (`mql5_kg/runtime.py`)
Adds runtime relationships that source calls cannot express: `runtime_dispatches`
(MetaTrader terminal → event handlers) and `may_trigger_event` (e.g. `OrderSend` →
`OnTradeTransaction`, timer registration → `OnTimer`). Runtime edges use `origin: "runtime"`
and are never confused with source `calls`.

### 6. Canonical graph (`mql5_kg/graph.py`, `mql5_kg/evidence.py`)
`CodeGraph` owns nodes, edges, diagnostics, metadata, schema version, and source fingerprint.
Every edge carries `origin` (extracted/resolved/runtime/inferred), `confidence`, and `location`.
Serialization is deterministic (`to_json` → canonical JSON) and file saves are atomic
(temp-file + rename).

### 7. Snapshots (`mql5_kg/snapshots.py`)
Analysis produces an immutable snapshot: build → validate → build index → validate → publish
atomically. Snapshots carry a deterministic source fingerprint so clients can detect staleness
(`graph_identity_mismatch`).

### 8. Index (`mql5_kg/index.py`)
An immutable `GraphIndex` with sorted node/edge maps, name/qualified-name lookups, and
incoming/outgoing adjacency tables. It never mutates the canonical graph.

### 8b. Incremental indexing (`mql5_kg/incremental.py`)
An optional persisted `FileCache` stores each file's content hash → serialized `ParseResult`
(versioned, deterministic). `incremental_analysis()` diffs current source content against the
cache, re-lexes/parses **only** changed/added files, reuses unchanged files' cached parse
results, and then runs the **full** deterministic `build_graph` resolution over the combined
units — so overload, include, and scope changes from one modified file resolve correctly for
every caller. A repository with no changes is reused wholesale (`mode: reuse`); a missing,
corrupt, or config-mismatched cache falls back to a full rebuild (`mode: full`). The cache and
graph are persisted atomically together (`persist_incremental`), preserving Invariant 5
(determinism) and Invariant 12 (no partial publication). Exposed via `mql5kg index --incremental`; the MCP server intentionally remains in-memory (its read-only, no-disk-write security
invariant), reusing a loaded snapshot by fingerprint instead.

### 9. Intelligence kernel (`mql5_kg/intelligence/`)
The single owner of query semantics:
`query`, `context`, `impact`, `path`, `diagnostics`, `context_package` — all over one immutable
index with bounded deterministic traversal, evidence preservation, and truthful completion
metadata (truncation reasons: `max_depth`, `max_items`, `max_paths`, `max_expansions`,
`context_budget`).

### 10. Context engine (`mql5_kg/context/engine.py`)
Generates compact AI-oriented context packages under an explicit `context_units` budget.
Relationships are packed atomically with both endpoint summaries; ranking is deterministic
(target → definition → direct callers/callees → dependencies → diagnostics → runtime → 2-hop →
lower-confidence inference); omissions are reported.

### 11. Adapters
- **CLI** (`adapters/cli.py`): `mql5kg` with `index`, `status`, `search`, `symbol`, `callers`,
  `callees`, `references`, `impact`, `trace`, `context`, `diagnostics`, `export`, `serve`;
  `--json` for machine-readable output.
- **HTTP** (`adapters/http.py`): stdlib HTTP API over the kernel (`/api/v1/...`).
- **MCP** (`adapters/mcp/`): stdio MCP server over kernel-backed sessions with read-only tools,
  fingerprint checks, and lifecycle logging on stderr only.
- **Compat** (`compat/`): legacy `graphify` CLI and `MQL5Parser` facade for existing scripts.

### 12. Optional isolated subsystems
- `reference/` — offline reference corpus (PDF → page-cited evidence), never graph truth.
- `integrations/graphify.py` — semantic overlay, always labeled `semantic_overlay_inference`.
- `compiler_evidence.py` — read-only MetaEditor log correlation.

## Performance notes

- Lexing and parsing are linear in tokens; function-body membership is O(1) per token via a
  precomputed token→function map (see `ANALYSIS.md` in the upstream `mql5-codegraph` for the
  original O(n·m) failure this design avoids).
- Incremental indexing (`--incremental`) skips the lex + parse + call-site extraction cost for
  unchanged files entirely (loaded from the persisted cache) while always running full
  repository-wide resolution for correctness.
- Graph queries run over immutable sorted indexes; context and path searches are bounded by
  explicit `max_depth`/`max_expansions`/`max_items` limits.

## Determinism

Canonical output (symbol IDs, edge IDs, ordering, search results, context ranking,
diagnostics, fingerprints) is fully deterministic for a given source tree and configuration.
See `docs/ai/DETERMINISM.md` notes inside `ARCHITECTURE_INVARIANTS.md` (Invariant 5).
