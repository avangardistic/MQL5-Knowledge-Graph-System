# Development

## Environment setup

```bash
# Clone and install in editable mode with dev extras
git clone https://github.com/avangardistic/MQL5-Knowledge-Graph-System.git
cd MQL5-Knowledge-Graph-System
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

> On Windows use Git Bash semantics: POSIX commands (`mv`, `rm`) — never
> `move`/`del`. The core runs on Windows, Linux, and macOS.

## Build

```bash
python -m compileall -q mql5_kg            # syntax check (fast)
pip install -e .                           # install package + entry points
```

Entry points after install: `mql5kg`, `mql5kg-mcp`, and legacy `graphify` /
`mql5-kg`.

## Code style

- Type-annotated Python (3.10+ syntax: `int | None`, `list[str]`, etc.).
- Modules carry a docstring; derived code notes
  "Portions derived from mql5-codegraph (MIT License)".
- Use `stable_id` for content-addressed identity and canonical sorted JSON for
  serialization — **determinism matters**.
- No `print` in library modules (adapters may write to stderr for
  human/server output); no debug leftovers.
- No third-party imports in the core (stdlib only). Optional deps live behind
  the `mcp` / `reference` extras.

## Test loop

```bash
python -m compileall -q mql5_kg
python -m pytest -q
mql5kg index sample_mql5 -o /tmp/graph.json --json       # CLI smoke
mql5kg trace /tmp/graph.json OnTick OrderSend
```

Run the full suite after any non-trivial change; add a test for your change
(see `docs/testing.md`).

## Project layout

```
mql5_kg/
├── lexer.py parser.py ir.py          # front-end
├── symbols.py scopes.py resolver.py   # models + resolution
├── runtime.py                         # runtime relationships
├── graph.py snapshots.py index.py     # canonical graph + index
├── indexer.py                         # end-to-end analysis
├── evidence.py diagnostics.py         # provenance + diagnostics
├── analysis_budget.py                 # deterministic work budget
├── intelligence/  context/            # kernel + context engine
├── reference/ compiler_evidence.py    # optional subsystems
├── adapters/{cli,http,mcp}/           # thin projections
├── compat/                            # legacy graphify + facade
├── exporters/ benchmarks/             # output + measurement
└── version.py
```

`docs/architecture.md` and `docs/ai/TARGET_ARCHITECTURE.md` describe the
design; `AGENTS.md` states the invariants every change must respect.

## Optional extras

- MCP: `pip install -e ".[mcp]"`
- Reference/build: `pip install -e ".[reference]"`
- Dev: `pip install -e ".[dev]"`

## CI

`.github/workflows/ci.yml` runs `pytest -v` and a CLI smoke test on Python
3.10 / 3.11 / 3.12 for every push/PR to `main`.