# Target Architecture

The final system is a layered pipeline. Each layer has one responsibility and consumes a
deterministic analysis budget. Adapters sit on top of the intelligence kernel and contain no
graph semantics.

```text
                         MQL5 SOURCE CODE
                                │
                                ▼
                       Source Discovery          indexer.py
                                │
                                ▼
                       Encoding / Input          indexer.py (utf-8-sig; DECODE_RECOVERY)
                         Normalization
                                │
                                ▼
                          MQL5 Lexer             lexer.py (recovery-oriented, precise coords)
                                │
                                ▼
                      Structural Parser          parser.py (tolerant, budgeted)
                                │
                                ▼
                         AST / IR Layer          ir.py (ParseResult/Declaration/CallSite)
                                │
                                ▼
                       Symbol Extraction         symbols.py (canonical kinds + identity)
                                │
                                ▼
                       Scope Resolution          scopes.py (global/class/function/block/param)
                                │
                                ▼
                       Include Resolution        resolver.py (relative/system/roots, guards)
                                │
                                ▼
                        Call Resolution          resolver.py (receiver/arity/qualified, ambiguity)
                                │
                                ▼
                       Runtime Enrichment        runtime.py (runtime_dispatches, may_trigger_event)
                                │
                                ▼
                   Canonical MQL5 CodeGraph      graph.py (schema-versioned, deterministic IDs)
                                │
                                ▼
                         Graph Validation        snapshots.py (invariant checks)
                                │
                                ▼
                         Immutable Graph          snapshots.py (atomic publication, fingerprint)
                                │
                                ▼
                           GraphIndex            index.py (immutable sorted indexes)
                                │
                                ▼
                      Intelligence Kernel        intelligence/kernel.py
             ┌──────────────────┼──────────────────┐
             │                  │                  │
             ▼                  ▼                  ▼
            CLI                HTTP               MCP
        adapters/cli.py   adapters/http.py   adapters/mcp/
             │                  │                  │
             └──────────────────┼──────────────────┘
                                │
                                ▼
                         AI Coding Agents
```

## Module map

| Layer | Module | Responsibility |
|---|---|---|
| Budget | `analysis_budget.py` | Deterministic work accounting; `AnalysisBudgetExceeded` |
| Diagnostics | `diagnostics.py` | Coded diagnostics: LEX/PARSE/RESOLVE/SOURCE + categories |
| Lexer | `lexer.py` | Tokens with line/column/offset; never reads strings/comments as code |
| Parser | `parser.py` | Tolerant structural extraction; brace/paren pairing; function ranges |
| IR | `ir.py` | `ParseResult`, `Declaration`, `CallSite`, `IncludeRef`, `SourceLocation` |
| Symbols | `symbols.py` | Canonical symbol kinds; identity rules (`file:`, `symbol:` IDs) |
| Scopes | `scopes.py` | Scope kinds and lexical preference rules |
| Resolver | `resolver.py` | Include + call + scope resolution; ambiguity preserved; external nodes |
| Runtime | `runtime.py` | Terminal/event/trading lifecycle enrichment |
| Evidence | `evidence.py` | Origins, evidence classes, confidence policy |
| Graph | `graph.py` | `CodeGraph`, `GraphNode`, `GraphEdge`, `stable_id`, schema version |
| Snapshots | `snapshots.py` | Immutable snapshots, fingerprints, atomic publication, validation |
| Index | `index.py` | Immutable `GraphIndex` (lookups + adjacency) |
| Context | `context/engine.py` | Budgeted deterministic context packages |
| Intelligence | `intelligence/` | Versioned contract models, errors, matching, traversal, paths, kernel |
| Indexer | `indexer.py` | Discovery + end-to-end `analyze_repository()` |
| Adapters | `adapters/cli.py`, `adapters/http.py`, `adapters/mcp/` | Thin adapters over the kernel |
| Exports | `exporters/` | GraphML, Markdown (JSON via `CodeGraph.to_json`) |
| Reference | `reference/` | Optional isolated offline reference corpus |
| Compiler evidence | `compiler_evidence.py` | Read-only MetaEditor log correlation |
| Integration | `integrations/graphify.py` | Optional semantic overlay (`shell=False`) |
| Compat | `compat/` | Legacy `graphify` CLI + `MQL5Parser` facade over the new core |

## Core principles encoded here

1. **Semantics live in the core** — adapters only project.
2. **Determinism everywhere** — sorted iteration, stable IDs, canonical JSON.
3. **Evidence on every edge** — origin + confidence + location.
4. **Ambiguity is data** — never collapsed by the resolver or the kernel.
5. **Budgets are mandatory** — analysis budget and context budget are enforced.
6. **Atomic publication** — the last valid graph survives any failure.
7. **Offline-first** — the core has no network dependency.
8. **Reference and inference are separate** — never become canonical truth.
