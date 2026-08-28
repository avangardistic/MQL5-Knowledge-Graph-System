# Getting Started

This guide walks through installing the system, indexing an MQL5 project, and
running your first queries.

## Prerequisites

- Python 3.10+ (tested through 3.13)
- An MQL5 project directory (files with `.mq5` / `.mqh` extensions)

## Installation

```bash
pip install -e .            # core (Python stdlib only)
pip install -e ".[mcp]"     # + MCP server for AI assistants
pip install -e ".[dev]"     # + pytest for development
```

The core has **zero required third-party dependencies**. The `mcp` extra is
needed only for the MCP server; `pypdf` / `pypdfium2` only for PDF reference
corpus building.

## Step 1 — Index a project

```bash
mql5kg index ./MQL5/Experts -o graph.json
```

This lexes, parses, resolves, and enriches every `.mq5` / `.mqh` file under
the root, validates the result, and saves one canonical graph. The command
prints:

```
Indexed 14 files: 412 nodes, 903 edges, 31 diagnostics -> graph.json
```

The graph save is atomic: a partially built graph is never written.

### Options

| Option | Meaning |
|--------|---------|
| `--include-root PATH` | Extra directory to resolve `#include` against (repeatable) |
| `--exclude NAME` | Directory *name* to skip, e.g. `--exclude Legacy` (repeatable) |
| `--max-work N` | Analysis work budget (deterministic logical units); safe failure if exhausted |
| `--json` | Machine-readable summary |

## Step 2 — Query the graph

Every query command takes the graph file as its first argument.

```bash
mql5kg search graph.json "position"       # fuzzy symbol search
mql5kg symbol graph.json ClosePosition    # exact resolution + definition
mql5kg callers graph.json ClosePosition   # who calls it
mql5kg callees graph.json OnTick          # what it calls
mql5kg impact graph.json CalculateRisk    # upstream impact of a change
mql5kg trace graph.json OnTick OrderSend  # directed execution paths
mql5kg context graph.json CloseBasket --budget 60   # AI-oriented package
mql5kg diagnostics graph.json             # parse/resolution diagnostics
```

Append `--json` to any query for the full machine-readable contract.

## Step 3 — Serve it

### HTTP API

```bash
mql5kg serve --graph graph.json --port 8765
```

Endpoints (see `docs/cli.md` / `docs/ai/INTELLIGENCE_CONTRACT.md`):

```
GET /api/v1/project
GET /api/v1/symbols?target=OnTick
GET /api/v1/search?q=position
GET /api/v1/context?target=ClosePosition
GET /api/v1/impact?target=CalculateRisk
GET /api/v1/trace?source=OnTick&target=OrderSend
GET /api/v1/context_package?target=OnTick&units=60
GET /api/v1/diagnostics
```

### MCP

```bash
mql5kg-mcp
```

Register this command with your MCP client (Claude Desktop, Cursor, etc.).
See `docs/mcp.md` for the full tool list and security model.

## What you can now ask an AI agent

With the graph indexed, an agent can answer, using only compact structural
context:

- Where is this symbol defined?
- Who calls this function?
- What does this function call?
- What breaks if I change this function?
- What is the execution path from `OnTick()` to `OrderSend()`?
- Which include introduced this dependency?
- Which relationships are source-backed and which are inferred?
- What was omitted when the context budget ran out?

## Next steps

- `docs/architecture.md` — how the system is built
- `docs/parser.md` — what MQL5 constructs are understood
- `docs/context-engine.md` — how token efficiency works
- `docs/benchmarking.md` — measured token-efficiency numbers
