# Capability Matrix — Repository Archaeology

Comparison of the two source repositories inspected during Phase 1:

- **Repository A (KG)**: `MQL5-Knowledge-Graph-System` @ `a56e532572690aaa616ee99eda5a745a75233d7c` (main)
- **Repository B (CodeGraph)**: `mql5-codegraph` @ `856cc91958c7f939a98278826c925289fec6911f` (main)

Both were read at source level (implementation, tests, docs, configs), not inferred from filenames.

| Capability | Repository A (KG) | Repository B (CodeGraph) | Quality | Reuse? | Rewrite? | Remove? |
|---|---|---|---|---|---|---|
| Lexer | None — regex scanning over stripped text | Recovery-oriented tokenizer with precise line/column/offset, unterminated-string/comment diagnostics | High | Yes (port) | Minor adaptation | No |
| Parser | Regex-only symbol extraction (functions, classes, structs, enums, inputs, globals, properties, defines) | Tolerant structural parser over tokens: declarations, call sites, include refs, brace/paren pairing, function ranges, budgeted | High | Yes (port) | Add method/scope binding detail | No |
| AST/IR | Implicit — regex match groups | `ParseResult` / `Declaration` / `CallSite` / `IncludeRef` records (IR layer) | Medium–High | Yes | Formalize as `ir` layer | No |
| Symbol extraction | Symbols keyed by bare name → collisions, no identity | Deterministic `stable_id()` nodes with kind + qualified name + signature | High | Yes | Add canonical `symbols` model + documented identity rules | No |
| Scope resolution | None — repository-wide name matching only | Qualified-name + receiver-type + arity preference, ambiguity preserved | Medium | Yes | Add explicit `scopes` model; keep ambiguity first-class | No |
| Include resolution | Records raw `#include` strings only; no resolution | Resolves relative/system/root/include-roots with traversal guard, unresolved diagnostics, confidence | High | Yes (port) | No |
| Call resolution | Function-body substring heuristic (5000-char window) — can mis-assign calls | Token-based call sites inside exact function ranges with receiver/arity resolution, ambiguity diagnostics | High | Yes (port) | No |
| Runtime enrichment | None | Terminal `runtime_dispatches` → event handlers; `may_trigger_event` (OrderSend → OnTradeTransaction, timers) | High | Yes (port) | No |
| Graph model | Dict-shaped `graph.json` (symbols/edges/files/includes/dll_imports) | Canonical `CodeGraph` with schema version, deterministic IDs, nodes/edges/diagnostics, atomic save | High | Yes (port) | No |
| Graph index | Query-time linear scans | Immutable `GraphIndex` with sorted lookups, incoming/outgoing adjacency, diagnostics ordering | High | Yes (port) | No |
| Diagnostics | None | Coded diagnostics (LEX/PARSE/RESOLVE/SOURCE) with severity + location | High | Yes (port) | Extend categories per §30 |
| Evidence model | None | Origin (`extracted`/`resolved`/`runtime`/`inferred`) + confidence + location on every edge | High | Yes (port) | Formalize as `evidence` module (§17) | No |
| Context generation | Symbol context (definition + callers/callees) | Deterministic budgeted `context_package` with ranking, atomic packing, omission reporting | High | Yes (port) | No |
| Search | Substring scan over symbols/files/types | Kernel `query` with rank-preserving resolution (exact/normalized/partial) | High | Yes (port) | No |
| Impact analysis | Reverse-CALLS scan, 50 dependent cap | Bounded upstream traversal with explicit relationship policy + completion metadata | High | Yes (port) | No |
| CLI | `graphify build/query/serve` (argparse) | `mql5-codegraph analyze/status/query/context/impact/intelligence/export/compiler-evidence/reference/serve` | High | Yes (port) | New `mql5kg` surface (§39) + compat shim | No |
| HTTP API | None | `web/` dashboard + HTTP API (stdlib) | High | Yes (port API) | Port `web/api.py` as stdlib HTTP adapter; drop React dashboard | Dashboard dropped |
| MCP | 6 tools over dict graph; SDK v1 decorator API; broken against installed SDK (baseline 26 errors) | FastMCP server over `ProjectSession`/`ReferenceSession`, lifecycle logging to stderr, read-only annotations, fingerprint checks | High | Yes (port) | New tool surface over kernel + legacy aliases | Old broken impl |
| Reference corpus | None | Full offline PDF→page/section corpus with hashes, authority, citations | High | Yes (port, optional extra) | No |
| Graphify | `graphify.py` CLI only (build/query/serve naming) | `reference/graphify_adapter.py` — subprocess overlay with `shell=False`, credential isolation | High | Yes (port as optional integration) | No |
| Compiler evidence | None | MetaEditor log correlation, staleness detection, no graph mutation | High | Yes (port) | No |
| Tests | 6 files; baseline broken (15 failed / 26 errors) | Extensive: lexer, parser, indexer, intelligence (6 files), mcp_adapter (3), reference_corpus (4), web, CLI, budget, compiler evidence | High | Yes (port ideas + fixtures) | New suite per §44 | Old suite replaced |
| CI | None | GitHub Actions `ci.yml` | High | Yes (port) | No |
| Documentation | README only | AGENTS.md, architecture, ADRs, project journal, limitations, releases | High | Yes (port ideas) | Full rewrite for both audiences (§53/§54) | No |
| Security | None — MCP unrestricted | Root containment, traversal guards, external-process hardening, read-only MCP | High | Yes (port) | No |
| Web dashboard | None | React/Vite dashboard | Medium | No | No | Yes — out of scope for final repo (keeps repo self-contained Python; HTTP API retained) |

## Summary judgment

- Repository B is the mature, evidence-backed implementation of nearly every required capability and should be **selectively integrated**.
- Repository A contributes the **product identity** (`MQL5-Knowledge-Graph-System`, `mql5_kg` package, `graphify` entry points), the MQL5 sample files, and the legacy CLI/MCP surface that must be **preserved as thin compatibility adapters**.
- No blind copy of either repo: the final repository gets one architecture (target in `target-architecture.md`), one canonical graph model, one intelligence kernel, and one public contract, with the legacy `graphify` surface projected over the new core.
