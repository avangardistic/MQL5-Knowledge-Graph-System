# MQL5 Knowledge Graph System

**Production-grade static analysis, knowledge graph, and AI intelligence platform for MQL5 codebases.**

[![Tests](https://github.com/avangardistic/MQL5-Knowledge-Graph-System/actions/workflows/ci.yml/badge.svg)](https://github.com/avangardistic/MQL5-Knowledge-Graph-System/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## What Is This?

**MQL5 Knowledge Graph System** is a complete platform that transforms MQL5 codebases into a precise, queryable, evidence-backed knowledge graph. It helps AI coding assistants understand code structurally and relationally while **dramatically reducing token consumption**.

Instead of feeding AI agents thousands of lines of source code, you give them compact structural context:

```text
OnTick
├── Callers: none (entry point)
├── Callees:
│   ├── CheckSignal
│   ├── OpenPosition
│   └── ManagePositions
├── Dependencies:
│   ├── Trade.mqh
│   └── PositionInfo.mqh
└── Impact: 12 dependent symbols
```

That is a few hundred tokens of structural context instead of thousands of tokens of dense source code — with evidence on every relationship, so the AI can trust *why* each edge exists.

---

## Why Does It Exist?

MQL5 coding agents face a fundamental problem:

- **MQL5 codebases are complex** — multiple files, deep includes, many dependencies
- **AI context windows are limited** — feeding entire source trees wastes tokens
- **AI needs structure** — understanding relationships is more important than reading every line

This system solves that by providing:

1. **Structural understanding** — not just text, but a graph of relationships
2. **Evidence-backed intelligence** — every relationship explains *why* it exists
3. **Token-efficient context** — compact packages with deterministic budgets
4. **AI-native interfaces** — MCP, CLI, and HTTP API

Ambiguity is preserved (never invented away). Evidence is preserved on every
edge (never silently upgraded). Analysis is deterministic (same source +
same configuration ⇒ same graph identity). Failed analysis never replaces the
last valid snapshot.

---

## Architecture

```text
                         MQL5 SOURCE CODE
                                │
                                ▼
                       Source Discovery
                                │
                                ▼
                          MQL5 Lexer
                                │
                                ▼
                      Structural Parser
                                │
                                ▼
                         AST / IR Layer
                                │
                                ▼
                       Symbol Extraction
                                │
                                ▼
                       Scope Resolution
                                │
                                ▼
                       Include Resolution
                                │
                                ▼
                        Call Resolution
                                │
                                ▼
                       Runtime Enrichment
                                │
                                ▼
                   Canonical MQL5 CodeGraph
                                │
                                ▼
                         Graph Index
                                │
                                ▼
                      Intelligence Kernel
                                │
             ┌──────────────────┼──────────────────┐
             │                  │                  │
             ▼                  ▼                  ▼
            CLI                API                MCP
             │                  │                  │
             └──────────────────┼──────────────────┘
                                │
                                ▼
                         AI Coding Agents
```

Every adapter is a thin projection over the **Intelligence Kernel**; no
adapter implements graph semantics. The core requires only the Python
standard library; `mcp`, `pypdf`, and `pypdfium2` are optional extras.

---

## Installation

```bash
# Core (Python standard library only)
pip install -e .

# Optional: MCP server support
pip install -e ".[mcp]"

# Optional: reference corpus build support (PDFs)
pip install -e ".[reference]"
```

Requires Python 3.10+.

---

## Quick Start

### 1. Index an MQL5 Project

```bash
mql5kg index /path/to/your/project -o graph.json
```

Re-index faster by reusing parsed unchanged files (and always running full,
correct resolution):

```bash
mql5kg index /path/to/your/project --incremental -o graph.json
```

### 2. Query the Graph

```bash
# Show project status
mql5kg status graph.json --json

# Search for a symbol
mql5kg search graph.json "OnTick"

# Show symbol details
mql5kg symbol graph.json OnTick

# Show callers / callees
mql5kg callers graph.json CalculateRisk
mql5kg callees graph.json OnTick

# Find references
mql5kg references graph.json Trade.mqh

# Impact analysis
mql5kg impact graph.json CalculateRisk
```

### 3. Get AI-Ready Context

```bash
# Compact context with a deterministic budget
mql5kg context graph.json OnTick --budget 50

# Trace execution path with per-hop evidence
mql5kg trace graph.json OnTick OrderSend

# Export graph (graphml | markdown | json)
mql5kg export graph.json --format graphml -o graph.graphml
```

Append `--json` to any command for full machine-readable output.

### 4. Use with MCP

```bash
# Start the MCP server (stdio)
mql5kg-mcp

# Connect from Claude, Cursor, or any MCP-compatible AI client
```

---

## Key Features

### 🔍 Tolerant Parser
- Handles incomplete, malformed, and partially edited code
- Preserves source locations (file, line, column)
- Immune to code-looking strings and comments (no phantom call edges)
- Parses large files in near-linear time

### 🧠 Canonical Knowledge Graph
- Symbols, scopes, files, and typed relationships
- Evidence-backed provenance (origin + confidence + location)
- Deterministic IDs and serialization; immutable snapshots

### 🔬 Intelligence Kernel
- Search symbols, callers, callees, references, dependencies
- Impact analysis, execution-path tracing
- Deterministic, versioned contract (`query`, `context`, `impact`, `path`, `context_package`, `diagnostics`)

### 📊 Context Engine
- Budgeted context packages with atomic relationship packing
- Deterministic ranking; truthful omission reporting
- Token-efficient output for AI agents

### ⚡ Incremental Indexing
- Persisted content-hash cache reuses parsed unchanged files
- Only changed/added files are re-parsed; resolution always runs fully (correct by construction)
- Safe fallback to a full rebuild on a missing or corrupted cache

### 🤖 MCP Integration
- AI-native interface, 16 read-only tools
- Security-bound filesystem access (project-root confinement)
- Snapshot-consistency fingerprint checks

### 📚 Optional Reference Corpus
- Offline PDF documentation ingestion
- Page-aware search with citations
- Separated from code-graph truth (never becomes graph truth)

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `index` | Index an MQL5 project into a graph (`--incremental`, `--cache`) |
| `status` | Show project graph status |
| `search` | Search for symbols |
| `symbol` | Get symbol details |
| `callers` | List all callers of a symbol |
| `callees` | List all callees of a symbol |
| `references` | Find references to a symbol or file |
| `impact` | Analyze impact of changes |
| `trace` | Trace execution paths |
| `context` | Get a budgeted AI context package |
| `diagnostics` | Show analysis diagnostics |
| `export` | Export graph (graphml \| markdown \| json) |
| `serve` | Start the HTTP API server |

All commands support `--json` for machine-readable output.

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `project_status` | Report the active in-memory snapshot |
| `index_project` | Read a trusted project into an in-memory graph |
| `search_symbols` | Search symbols by name/qualified name |
| `get_symbol` | Resolve one symbol (definition + location) |
| `get_symbol_context` | Bounded context: definition, callers, callees, dependencies |
| `find_callers` | Who calls this symbol? |
| `find_callees` | What does this symbol call? |
| `find_references` | All references to a symbol |
| `find_dependencies` | File/symbol dependencies (includes, defines) |
| `get_file_summary` | File location, line count, defined symbols |
| `resolve_include` / `resolve_includes` | Resolve single / recursive include chains |
| `impact_analysis` | Bounded upstream impact of a change |
| `trace_execution_flow` | Directed paths with per-hop evidence |
| `get_diagnostics` | Ordered graph diagnostics |
| `get_context_package` | Budgeted context package for AI review |

Every tool is read-only, bounded, and confined to the operator-selected
project root.

---

## Token Efficiency

**Real measured results** (recorded under `docs/benchmarks/`):

For a representative 40-file, ~455 KB MQL5 repository, a fixed-budget
(60-unit) structural context package for one symbol:

| Context Type | Estimated Tokens |
|--------------|------------------|
| Raw source (all files) | ~113,700 |
| Graph context package (60 units) | ~10,900 |

The context package is **~9.6%** of the raw source tokens while carrying
the symbol's definition, direct callers/callees, dependencies, and
diagnostics with evidence. Numbers are measured with a conservative
`chars / 4` token estimate — no unsupported savings are claimed (see
`docs/benchmarking.md` for methodology, including the honest note that on a
tiny 2-file repo a large fixed package can exceed raw source).

---

## Security

- **MCP filesystem access** is restricted to the authorized project root (+ explicit include roots)
- **Path traversal attempts** (`../`, absolute paths, symlink escapes) are rejected
- **No credentials** are stored or transmitted; subprocess env is restricted
- **Graphify/LLM** inference is optional, isolated, and labeled `semantic_overlay_inference`
- **Reference corpus** is offline, hash-verified, and operator-controlled

See `docs/security.md` and `docs/ai/SECURITY_MODEL.md`.

---

## Development

```bash
pip install -e ".[test]"     # pytest, pytest-asyncio, mcp

python -m pytest -v          # full suite (208 tests)
mql5kg index sample_mql5 -o graph.json --json   # CLI smoke test
python -m mql5_kg.benchmarks.token_efficiency sample_mql5 --symbol OnTick
```

CI (`.github/workflows/ci.yml`) runs the full suite on Python 3.10 / 3.11 /
3.12 on every push/PR to `main`.

---

## Documentation

| Audience | Location |
|----------|----------|
| Human | [`docs/`](docs/) |
| AI Agent | [`docs/ai/`](docs/ai/) |
| Agent Instructions | [`AGENTS.md`](AGENTS.md) |
| Final Report | [`FINAL_REPORT.md`](FINAL_REPORT.md) |

---

## Known Limitations

- **Analysis budget**: the default 1M-unit budget supports roughly ~250 KB of dense source. Larger projects must raise `--max-work` (documented in `docs/configuration.md`).
- **Type inference** is best-effort; ambiguous overloads are preserved as ambiguous rather than guessed (by design).
- **Incremental indexing is parse-incremental, not resolution-incremental**: unchanged files skip re-parsing, but repository-wide resolution always runs to guarantee correctness.
- **Reference corpus**: implemented and security-tested, but requires operator-supplied PDFs and, for the optional Graphify overlay, the external `graphify` binary + a supported backend.

---

## Roadmap

- [x] Core tolerant lexer and structural parser
- [x] Canonical evidence-backed knowledge graph + immutable snapshots
- [x] Intelligence Kernel (`query`, `context`, `impact`, `path`, `context_package`, `diagnostics`)
- [x] Budgeted context engine with omission reporting
- [x] Sound incremental indexing (`--incremental`)
- [x] MCP integration (16 read-only, security-bound tools)
- [x] CLI and HTTP API adapters
- [x] Test suite (208 tests: unit, adversarial, security, invariants, wire protocol, incremental)
- [x] Human and AI documentation
- [x] CI/CD workflow (Python 3.10–3.12)
- [ ] Git-diff-aware change analysis (index only files changed since a commit)
- [ ] VS Code extension
- [ ] GitHub Action integration

---

## Contributing

Please read [`docs/contributing.md`](docs/contributing.md) before proposing changes.

---

## License

MIT License. See [`LICENSE`](LICENSE).

## Credits

This project is a fundamental rewrite of the original `MQL5-Knowledge-Graph-System`, incorporating proven ideas from `mql5-codegraph`. Both repositories are by the same author and are MIT-licensed. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

---

## Community

- ⭐ **Star** this repository to help others discover it
- 🐛 **Report issues** through GitHub Issues
- 💬 **Start discussions** in GitHub Discussions
- 🔒 **Report vulnerabilities** through GitHub's security reporting

---

**Built for MQL5 developers and AI coding agents.**