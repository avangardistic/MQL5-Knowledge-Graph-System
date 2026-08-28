# Rewrite Report — What Has Been Done So Far

This report summarizes all work completed to date on the fundamental rewrite
of the **MQL5 Knowledge Graph System**. It tells you exactly what was built,
in what order, what passes, and what still remains.

---

## 1. Mission recap

Rewrite the `MQL5-Knowledge-Graph-System` repository into a production-grade
**MQL5 parser + static-analysis engine + canonical knowledge graph +
code-intelligence kernel + AI/MCP integration platform**, taking architecture
and ideas from `mql5-codegraph` (source of inspiration only — **not** a
dependency). Primary business goal: **reduce AI token consumption** by giving
agents compact, evidence-backed structural context instead of entire source
trees.

---

## 2. What was found at the start (PHASE 1 — archaeology)

- **Repo A (`MQL5-Knowledge-Graph-System`)** — the target, but small and
  broken. 35 files. Its baseline test suite did **not** pass (15 failed,
  26 errors) due to MCP SDK drift. It was regex-based, with no real parser,
  no evidence model, no intelligence kernel.
- **Repo B (`mql5-codegraph`)** — mature (268 files): a real lexer, tolerant
  parser, canonical graph, GraphIndex, Intelligence Kernel, context engine,
  reference corpus, MCP. But its package was split across many files and tied
  to its own module name.

**Decision:** keep Repo A's identity (`mql5_kg` package, MQL5
Knowledge-Graph-System name), and rewrite it from Repo B's proven ideas —
not a blind copy, but a coherent single architecture with new subsystems.

---

## 3. Planning documents written (PHASES 2–4)

These are committed under `docs/`:

| Document | Purpose |
|----------|---------|
| `docs/rewrite/capability-matrix.md` | Compares both repos capability-by-capability (reuse / rewrite / remove) |
| `docs/rewrite/architecture-comparison.md` | Deep comparison of the two architectures |
| `docs/rewrite/migration-plan.md` | Step-by-step rewrite plan |
| `docs/rewrite/discarded-components.md` | What was deliberately thrown away |
| `docs/rewrite/target-architecture.md` | The target layout |
| `docs/ai/ARCHITECTURE_INVARIANTS.md` | 12 non-negotiable rules (canonical graph, evidence, determinism, security, etc.) |
| `docs/ai/TARGET_ARCHITECTURE.md` | AI-oriented target architecture |
| `docs/architecture.md` | Human-oriented architecture |

---

## 4. Core implementation (PHASE 5+) — what now exists

All under the `mql5_kg/` package (total ~2800+ LOC of tested core):

**Front-end**
- `lexer.py` — tolerant MQL5 lexer; strings/comments immune to calls
- `parser.py` — structural parser: functions, methods, constructors,
  destructors, event handlers, classes/structs/enums, `#define`, `#property`,
  `input`/`sinput`, `#import` blocks; preserves source locations; survives
  broken source
- `ir.py`, `symbols.py`, `scopes.py` — canonical IR, symbol + scope models

**Analysis**
- `resolver.py` — include resolution, scope-aware call resolution,
  ambiguity preservation (`resolved` / `ambiguous` / `unresolved` /
  `inferred`)
- `runtime.py` — runtime/event relationships kept **separate** from source
  calls
- `diagnostics.py`, `evidence.py` — machine-readable diagnostics and the
  evidence vocabulary (origin, confidence, category)
- `analysis_budget.py` — deterministic logical work budget; safe fail; no
  partial graph published

**Graph layer**
- `graph.py` — canonical `CodeGraph` (nodes, edges, diagnostics, metadata,
  fingerprint, deterministic serialization, atomic save)
- `snapshots.py` — immutable snapshot publication + validation
- `index.py`, `indexer.py` — deterministic `GraphIndex` + end-to-end indexing

**Intelligence**
- `intelligence/` — versioned contract models, errors, matching, traversal,
  path finding, and the **IntelligenceKernel** (query, context, impact, path,
  context_package, diagnostics)
- `context/engine.py` — budgeted context engine; atomically packs
  relationships; truthfully reports omissions
- `benchmarks/token_efficiency.py` — measures token efficiency (does not
  claim without numbers)

**Adapters (thin projections over the kernel)**
- `adapters/cli.py` — the `mql5kg` CLI (index/status/search/symbol/callers/
  callees/references/impact/trace/context/diagnostics/export/serve, `--json`)
- `adapters/http.py` — stdlib HTTP API over `/api/v1/`
- `adapters/mcp/` — `service.py` (stateful kernel-backed sessions +
  security/normalization) and `server.py` (FastMCP stdio server, full tool set)
- `compat/` — legacy `graphify` CLI + legacy `MQL5Parser` facade (unchanged
  shape for existing users)
- `reference/` — optional isolated reference corpus + Graphify overlay
- `compiler_evidence.py` — external compiler-log correlation (optional)
- `exporters/` — graphml / markdown / json

**Public surface**
- `pyproject.toml` — package `mql5-kg` v2.0.0 with entry points `mql5kg`,
  `mql5kg-mcp`, plus legacy `graphify` / `mql5-kg`
- `THIRD_PARTY_NOTICES.md` — MIT attribution for derived code (Repos same
  author, MIT)

---

## 5. Tests — current status

**197 tests pass** (`python -m pytest`). Test files cover:
- lexer, parser, symbols, resolver, graph, snapshots, index, intelligence,
  context, runtime, analysis budget, diagnostics
- CLI, HTTP, MCP (service + real wire protocol), compatibility
- **adversarial** fixtures (broken source, deep/circular include chains,
  missing includes, `#import`, code-looking strings)
- **security** (path traversal, absolute paths, budget limits, fingerprint
  mismatch)
- **regression**, **compiler evidence**, **token benchmark**

### Recent fixes that made the suite pass
- O(n²) parser binding phase refactored to precomputed maps (fixes budget
  blowup on large repos)
- Destructor detection (`~Widget()`) fixed — was being classified as
  constructor
- `GraphNode` made hashable (content-addressed by `id`) so nodes work in sets
- Trace path rendering now shows symbol names (kernel now returns path nodes)
- MCP error-envelope wire test fixed (FastMCP prefixes error text)
- Token benchmark sized to a representative ~450KB repo with a measured
  **<10%** graph-context claim; `max_work` parameter added

---

## 6. Verification runs (real, measured)

- `sample_mql5` indexes to **51 nodes, 93 edges, 24 diagnostics**
- `mql5kg context ... --budget 20` respects the budget and reports omissions
  (`omitted diagnostics: 24`, `omitted nodes: 19`, `omitted relationships: 49`)
- `mql5kg trace OnTick OrderSend` returns 3 ranked paths:
  - `OnTick -> OpenBuyOrder -> MQL5::OrderSend`
  - `OnTick -> CloseAllPositions -> ClosePosition -> MQL5::OrderSend`
  - `OnTick -> TrailPositions -> ModifyPositionSL -> MQL5::OrderSend`
- Token benchmark recorded under `docs/benchmarks/token-efficiency-sample.json`
  (honest note: for a tiny 2-file repo the raw source beats a large package;
  the meaningful win is for representative multi-file repos)
- MCP stdio wire protocol exercised end-to-end (tools listed, index+query
  round-trip, error envelopes)

---

## 7. What was removed / cleaned

- Old `mql5_kg/parser/`, `mql5_kg/storage/`, `mql5_kg/mcp_server/` were
  deleted (replaced by the new architecture)
- Stale generated artifacts removed: `graph.json`, `GRAPH_REPORT.md`,
  `AUDIT_BASELINE.md`, `FINAL_AUDIT.md`
- `mql5_kg.egg-info/` and all `__pycache__/` tracked files removed
- `.gitignore` rewritten (was accidentally a commit message; now a proper
  ignore file)

---

## 8. Documentation — human + AI

**Done:**
- New README.md (accurate, describes the rewritten system)
- `docs/getting-started.md`, `docs/parser.md`, `docs/graph.md`,
  `docs/intelligence.md`, `docs/context-engine.md`, `docs/cli.md`,
  `docs/mcp.md`
- `THIRD_PARTY_NOTICES.md`

**Still to write (in progress):**
- `docs/reference-corpus.md`, `docs/graphify.md`, `docs/configuration.md`,
  `docs/security.md`, `docs/testing.md`, `docs/benchmarking.md`,
  `docs/development.md`, `docs/troubleshooting.md`, `docs/contributing.md`
- `AGENTS.md`
- `docs/ai/` reference set (`SYSTEM_OVERVIEW`, `GRAPH_SCHEMA`,
  `SYMBOL_MODEL`, `RELATIONSHIP_MODEL`, `EVIDENCE_MODEL`,
  `RESOLUTION_MODEL`, `INTELLIGENCE_CONTRACT`, `CONTEXT_ENGINE`,
  `MCP_TOOLS`, `ERROR_MODEL`, `SECURITY_MODEL`, `EXTENSION_GUIDE`,
  `TESTING_GUIDE`, `CHANGE_GUIDE`)
- `FINAL_REPORT.md` (deliverable from the master prompt)

---

## 9. Known limitations (honest)

- **Analysis work budget**: the default 1M-unit budget supports roughly
  ~250KB of dense source before `AnalysisBudgetExceeded`. Larger projects
  must raise `--max-work`. (This is by design — deterministic safe fail — but
  documented so operators know.)
- **Return-type / type inference** is best-effort; ambiguous calls are
  preserved as ambiguous rather than guessed.
- **No full incremental indexing** yet — re-indexing is whole-graph (safe but
  not incremental).
- **No CI workflow committed yet** (the master prompt calls for one; not yet
  added).
- The reference corpus and Graphify overlay are implemented but not yet
  end-to-end tested against real PDFs.
- Documentation set is partially complete.

---

## 10. What remains before final submission

1. Finish the human docs set (`reference-corpus`, `graphify`,
   `configuration`, `security`, `testing`, `benchmarking`, `development`,
   `troubleshooting`, `contributing`)
2. Write `AGENTS.md`
3. Write the `docs/ai/` reference set
4. Write `FINAL_REPORT.md`
5. Optional: add a CI workflow (GitHub Actions) that runs `pytest`
6. Final audit — confirm no secrets, repo is self-contained, deterministic
   rebuild works
7. Commit the work in a clean series and push

---

## 11. How to check the status yourself

```bash
cd MQL5-Knowledge-Graph-System
python -m pytest -q                # expect: 197 passed
mql5kg index sample_mql5 -o /tmp/graph.json
mql5kg trace /tmp/graph.json OnTick OrderSend
```