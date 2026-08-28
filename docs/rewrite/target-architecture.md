# Target Architecture — Rewrite Blueprint

The full design lives in `../ai/TARGET_ARCHITECTURE.md` and `../architecture.md`. This document
records the concrete module layout chosen for the rewrite and the rationale.

## Package layout (`mql5_kg/`)

```text
mql5_kg/
├── __init__.py               public API surface
├── version.py                single version source
├── analysis_budget.py        deterministic work budget (per §31)
├── diagnostics.py            coded diagnostics (per §30)
├── evidence.py               evidence model: origins/classes/confidence (per §17)
├── lexer.py                  MQL5 tokenizer (per §10)
├── ir.py                     IR records: ParseResult/Declaration/CallSite/IncludeRef
├── parser.py                 tolerant structural parser (per §9)
├── symbols.py                canonical symbol model + identity rules (per §11)
├── scopes.py                 scope model (per §12)
├── resolver.py               include + call + scope resolution (per §13/§14/§15)
├── runtime.py                runtime enrichment (per §18)
├── graph.py                  canonical CodeGraph (per §19)
├── snapshots.py              immutable snapshots + atomic publication (per §20/§67/§68)
├── index.py                  GraphIndex (per §21)
├── indexer.py                discovery + end-to-end analysis (per §2 pipeline)
├── context/
│   ├── __init__.py
│   └── engine.py             budgeted context packages (per §24/§25)
├── intelligence/
│   ├── __init__.py           re-exports
│   ├── models.py             versioned contract models (per §37)
│   ├── errors.py             machine-readable error model (per §38)
│   ├── matching.py           ambiguity-preserving symbol matching
│   ├── traversal.py          bounded context/impact traversal (per §27)
│   ├── paths.py              evidence-first directed path search (per §28)
│   └── kernel.py             IntelligenceKernel (per §22)
├── adapters/
│   ├── __init__.py
│   ├── cli.py                mql5kg CLI (per §39)
│   ├── http.py               HTTP API (per §40)
│   └── mcp/
│       ├── __init__.py
│       ├── service.py        kernel-backed sessions (per §36)
│       └── server.py         MCP adapter (per §34/§35)
├── exporters/
│   ├── __init__.py
│   ├── graphml.py            GraphML export (per §74)
│   └── markdown.py           human report generation
├── reference/                optional isolated reference corpus (per §32)
│   ├── __init__.py
│   ├── models.py
│   ├── builder.py
│   └── corpus.py
├── compiler_evidence.py      read-only compiler correlation (per §73)
├── integrations/
│   ├── __init__.py
│   └── graphify.py           optional semantic overlay (per §33/§50)
└── compat/                   legacy adapters over the new core (per §58/§59)
    ├── __init__.py
    ├── graphify.py           legacy `graphify` CLI + `mql5_kg.cli.graphify` path
    └── legacy_parser.py      deprecated MQL5Parser facade
```

## Rationale for deviations from the §4 sketch

- **`index/` merged into `index.py`** — one module; no empty package indirection.
- **`intelligence/index.py` hoisted to `index.py`** — the immutable index is a core artifact
  shared by the kernel, not an intelligence-private detail.
- **`ast/` absorbed into `ir.py`** — the tolerant parser produces IR records directly; a full
  AST adds indirection without semantic value for this analyzer (documented in `docs/parser.md`).
- **`reference/` stays a package** — it is genuinely independent and optional.
- **`context/` is a package** — the context engine is a first-class layer per §24–§26.

## Contracts

- Graph schema: `1.0.0` (`graph.py:SCHEMA_VERSION`).
- Intelligence contract: `1.0.0` (`intelligence/models.py:CONTRACT_VERSION`).
- Reference contract: `1.0.0` (`reference/models.py:CONTRACT_VERSION`).
- Compiler-evidence contract: `1.0.0` (`compiler_evidence.py:CONTRACT_VERSION`).
