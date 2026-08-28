# Migration Plan — Rewrite of MQL5-Knowledge-Graph-System

## Goal

Transform Repository A into a production-grade MQL5 parser + static analyzer + canonical
knowledge graph + code-intelligence platform, selectively integrating Repository B's proven
implementation without creating a runtime dependency on it.

## Phases

### Phase 0 — Git safety (done)
- Repo A HEAD: `a56e532572690aaa616ee99eda5a745a75233d7c` (branch `main`, clean, remote `origin` → `https://github.com/avangardistic/MQL5-Knowledge-Graph-System`).
- Repo B HEAD: `856cc91958c7f939a98278826c925289fec6911f` (branch `main`, clean).
- No upstream repository is modified. Repo B stays untouched; its code is *copied and adapted*
  (MIT license, attribution preserved) so the final repo is self-contained.

### Phase 1 — Archaeology (done)
See `capability-matrix.md` and `architecture-comparison.md`.

### Phase 2 — Planning documents (done)
`docs/rewrite/capability-matrix.md`, `docs/rewrite/architecture-comparison.md`,
`docs/rewrite/migration-plan.md`, `docs/rewrite/discarded-components.md`,
`docs/rewrite/target-architecture.md`, `docs/ai/ARCHITECTURE_INVARIANTS.md`,
`docs/architecture.md`, `docs/ai/TARGET_ARCHITECTURE.md`.

### Phase 3 — Core pipeline
1. `analysis_budget.py` — deterministic work budget (ported).
2. `diagnostics.py` — coded diagnostics (ported, extended categories).
3. `lexer.py` — recovery-oriented tokenizer (ported).
4. `ir.py` — `ParseResult`/`Declaration`/`CallSite`/`IncludeRef` (ported).
5. `parser.py` — tolerant structural parser (ported; `parse_source()` public).
6. `symbols.py` — canonical symbol kinds + deterministic identity rules (new).
7. `scopes.py` — scope model and lexical preference rules (new).
8. `resolver.py` — include + call + scope resolution, ambiguity preserved (ported + scopes).
9. `runtime.py` — runtime enrichment (ported).
10. `evidence.py` — evidence categories/origins/confidence policy (new, documents §17).
11. `graph.py` — canonical `CodeGraph` (ported; `SCHEMA_VERSION = "1.0.0"`).
12. `snapshots.py` — immutable snapshot publication + fingerprints (new, §20/§67/§68).
13. `indexer.py` — discovery + end-to-end analysis with budget + fingerprint (ported).
14. `index.py` — immutable `GraphIndex` (ported, hoisted out of `intelligence/`).

### Phase 4 — Intelligence layer
- `intelligence/models.py` (contracts), `intelligence/errors.py` (machine-readable errors),
  `intelligence/matching.py` (ambiguity-preserving resolution), `intelligence/traversal.py`,
  `intelligence/paths.py` (evidence-first path search), `context/engine.py` (budgeted context
  packages), `intelligence/kernel.py` (facade). All ported from Repository B.

### Phase 5 — Adapters
- `adapters/cli.py` — new `mql5kg` CLI (§39): index, status, search, symbol, callers, callees,
  references, impact, trace, context, diagnostics, export, serve; `--json` for machine output.
- `adapters/http.py` — stdlib HTTP API over the kernel (§40).
- `adapters/mcp/service.py` + `adapters/mcp/server.py` — MCP over the kernel (§34/§35/§36),
  including the six legacy tool names as aliases.
- `compat/graphify.py` — legacy `graphify` CLI and `mql5_kg.cli.graphify` module path as thin
  adapters over the new core; keeps `graphify`/`mql5-kg` console scripts working.
- `compat/legacy_parser.py` — deprecated `MQL5Parser` facade producing the legacy dict shape
  from the new pipeline (for existing scripts); removed in a future major.

### Phase 6 — Optional subsystems (isolated)
- `reference/` — offline reference corpus (ported; optional `[reference]` extra).
- `integrations/graphify.py` — semantic overlay subprocess with `shell=False` (ported).
- `compiler_evidence.py` — MetaEditor log correlation (ported).
- `exporters/` — GraphML (ported) + Markdown report (new).

### Phase 7 — Tests
New suite per §44–§49, porting Repository B's fixtures/ideas and adding Repo A's MQL5 fixtures.

### Phase 8 — Documentation
README, docs/* (human), docs/ai/* (AI), AGENTS.md (§53–§56).

### Phase 9 — Quality gates and publication
Run all gates (§82), adversarial audit (§83), final-audit doc (§84), logical commit series
(§85), push to `https://github.com/avangardistic/MQL5-Knowledge-Graph-System` (§87), and
`FINAL_REPORT.md` (§88).

## Backward compatibility decisions (§58)

| Existing surface | Decision | Implementation |
|---|---|---|
| `python -m mql5_kg.cli.graphify build/query/serve` | Preserve | Thin compat module projecting onto new engine/kernel |
| Console scripts `graphify`, `mql5-kg` | Preserve | Aliases to new CLI entry |
| Six legacy MCP tool names | Preserve | Registered as aliases over kernel operations |
| `MQL5Parser` class + dict graph shape | Deprecate | `compat.legacy_parser` facade, documented deprecated |
| `graph.json` shape | Deprecate | New canonical schema; old shape emittable by compat facade |

## Dead code policy (§59)

Every legacy module is either integrated (CLI surface, MCP names), replaced (parser, storage,
MCP implementation), or explicitly documented (legacy parser facade). No abandoned duplicates.
