# AGENTS.md

Instructions for AI coding agents working on this repository.

## Project purpose

The **MQL5 Knowledge Graph System** is a production-grade MQL5 parser,
static-analysis engine, canonical knowledge graph, code-intelligence kernel,
and AI integration platform. Its primary goal is to let AI coding agents
reason about MQL5 codebases structurally and relationally using **compact,
evidence-backed context** instead of the entire source tree — reducing AI
token consumption without sacrificing correctness or evidence.

## Architecture

Clean, layered, adapter-independent. The semantic logic lives in the core;
adapters are thin projections.

```
lexer → parser → (ir/symbols/scopes) → resolver → runtime → CodeGraph
                                                              │
                                             GraphSnapshot (immutable)
                                                              │
                                                        GraphIndex
                                                              │
                                                   IntelligenceKernel
                                                              │
                                              ┌───────────────┼───────────────┐
                                              ▼               ▼               ▼
                                             CLI             HTTP            MCP
```

Package layout (`mql5_kg/`):

| Path | Responsibility |
|------|----------------|
| `lexer.py`, `parser.py`, `ir.py` | Tolerant MQL5 front-end (no regex-only parsing) |
| `symbols.py`, `scopes.py` | Canonical symbol + scope models |
| `resolver.py` | Include, scope, call resolution; ambiguity preservation |
| `runtime.py` | Runtime/event relationships (never source `calls`) |
| `graph.py` | Canonical `CodeGraph`, deterministic serialization |
| `snapshots.py` | Immutable snapshot validation + publication |
| `evidence.py`, `diagnostics.py` | Provenance vocabulary + machine-readable diagnostics |
| `analysis_budget.py` | Deterministic analysis work budget |
| `index.py`, `indexer.py` | Deterministic `GraphIndex` + end-to-end analysis |
| `incremental.py` | Sound incremental analysis (persisted content-hash `FileCache`, parse unchanged files, always full resolution) |
| `intelligence/` | Intelligence Kernel + versioned contract models |
| `context/` | Budgeted context engine |
| `reference/` | Optional reference corpus + Graphify overlay (isolated) |
| `compiler_evidence.py` | Optional compiler-log correlation |
| `adapters/` | `cli`, `http`, `mcp` (thin projections over the kernel) |
| `compat/` | Legacy `graphify` CLI + legacy `MQL5Parser` facade |
| `exporters/` | graphml / markdown / json |
| `benchmarks/` | Token-efficiency measurement |

## Non-negotiable invariants

Read `docs/ai/ARCHITECTURE_INVARIANTS.md` in full. The twelve invariants:

1. **Canonical graph** — exactly one authoritative `CodeGraph` per analysis.
2. **Semantic core** — graph semantics live in the core, never in adapters.
3. **Evidence** — relationships preserve origin and evidence.
4. **Uncertainty** — ambiguity stays ambiguous; never invent certainty.
5. **Determinism** — same source + config ⇒ same graph identity and results.
6. **Snapshot consistency** — one request never mixes graph revisions.
7. **Security boundary** — MCP/HTTP never expand filesystem access.
8. **Context budgets** — explicit, deterministic, enforced.
9. **Adapter independence** — removing MCP never breaks the parser/kernel.
10. **Reference separation** — docs never silently become graph truth.
11. **Semantic overlay separation** — Graphify/LLM inference stays labeled.
12. **No partial publication** — failed analysis never replaces the last valid graph.

Do not violate these to make a change more convenient.

## Parser rules

- The lexer must keep strings and comments immune: code-like text inside them
  never becomes a call edge or symbol (`"OrderSend(foo)"` and `// ClosePosition()`
  must not create relationships).
- The parser must **tolerate** incomplete, malformed, and partially edited
  source, and emit diagnostics instead of crashing (see the adversarial
  fixtures in `tests/fixtures/adversarial/`).
- Preserve source locations (`file`, `line`, `column`).
- The parser is structural, not regex-only. Do not replace it with a fragile
  regex matcher.
- Large files must parse in near-linear time (the token→function map is
  precomputed once — do not reintroduce the O(functions × bindings) bug).

## Evidence rules

Every important edge carries `origin` (`extracted` | `resolved` | `runtime` |
`inferred`), `confidence`, and source `location` where available. Evidence
categories are `code_graph`, `reference_document`, `external_compiler_evidence`,
`semantic_overlay_inference`. Never silently upgrade a relationship's origin
or confidence. The graph must always be able to explain *why a relationship
exists*.

## Testing and build commands

```bash
python -m pytest -q                 # full suite (208 tests)
python -m pytest tests/test_parser.py   # single file
python -m compileall -q mql5_kg     # syntax check the package
mql5kg index sample_mql5 -o /tmp/graph.json --json   # CLI smoke test
pip install -e ".[dev]"             # dev dependencies (pytest, pytest-asyncio, mcp)
```

Run `python -m pytest` after any non-trivial change. Add a test that exercises
your change. The suite includes unit, regression, incremental (reuse / changed re-parse /
determinism vs full rebuild / corrupt-cache fallback), adversarial, security,
invariant/property, and wire-protocol MCP tests.

## MCP rules and security

- MCP is a read-only adapter over the Intelligence Kernel. It never
  implements graph semantics, writes to disk, invokes external tools, or
  accesses the network.
- Filesystem access is confined to the operator-selected project root (+
  explicit `include_roots`). Reject `..` traversal, absolute-path injection,
  and symlink escapes.
- All tool inputs are validated; all results are bounded; budgets are
  enforced; errors are machine-readable envelopes (never stack traces).
- `expected_source_fingerprint` guards against mixing snapshots.
- See `docs/ai/SECURITY_MODEL.md` and `docs/security.md`.

## Documentation rules

- Documentation targets two audiences: **humans** (`docs/`) and **AI agents**
  (`docs/ai/`). Keep both in sync with code.
- If you change a contract ("1.0.0"), bump it and update
  `docs/ai/INTELLIGENCE_CONTRACT.md` and `docs/ai/CHANGE_GUIDE.md`.
- Never make unmeasured token-savings claims. Run `benchmarks/token_efficiency.py`
  and record real numbers in `docs/benchmarks/`.
- `README.md`, `AGENTS.md`, and `FINAL_REPORT.md` must reflect reality.

## How to modify the graph schema

1. Update `mql5_kg/graph.py` (e.g. `SCHEMA_VERSION`, node/edge fields).
2. Add matching serialization in `to_dict`/`from_dict` (deterministic).
3. Update `docs/ai/GRAPH_SCHEMA.md` and `docs/ai/CHANGE_GUIDE.md`.
4. Bump the schema/contract version and follow the versioning rules.
5. Add round-trip tests (`tests/test_snapshots.py`) and update golden fixtures.
6. Run the full test suite.

## What must never be changed casually

- The `IntelligenceRequest`/`IntelligenceResult` contract shapes without a
  version bump.
- The evidence vocabulary or origin semantics (adapters and AI clients
  depend on them).
- The MCP security boundary (root confinement, path/type rejection).
- Determinism guarantees (no unordered hash iteration, no random IDs, no
  filesystem-order dependence in canonical results).
- The budget enforcement (context units and analysis work must stay bounded;
  omissions must always be reported).
- Legacy compatibility entry points (`graphify`, `MQL5Parser`) without
  documenting the break.

## Technology notes

- Python 3.10+; the core uses only the standard library. The `mcp`,
  `pypdf`, and `pypdfium2` dependencies are optional extras.
- `mql5-codegraph` is a source of ideas and patterns only — it is **not** a
  runtime dependency. Preserve attribution in `THIRD_PARTY_NOTICES.md`.
- Determinism matters: use `stable_id` for node/edge identity and canonical
  sorted JSON for serialization.