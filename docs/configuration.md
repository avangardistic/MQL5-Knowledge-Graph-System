# Configuration

The system is configured primarily through CLI flags and API/contract
parameters. There is no global config file — every option is explicit,
deterministic, and scoped to a single request or operation.

## Analysis parameters (`mql5kg index`)

| Parameter | CLI flag | Default | Meaning |
|-----------|----------|---------|---------|
| Project root | positional `root` | — | Directory scanned for `.mq5` / `.mqh` files |
| Output path | `--output` / `-o` | `graph.json` | Where the canonical graph is saved (atomic) |
| Include roots | `--include-root` | none | Extra directories to resolve `#include` against (repeatable) |
| Excluded dirs | `--exclude` | default set | Directory *names* to skip |
| Analysis budget | `--max-work` | `1000000` | Deterministic logical work units |

The default excluded names are `{".git", ".gitnexus", "graphify-out",
"build", "dist", "__pycache__"}`. Additional names via `--exclude` are added
to this set. **`--exclude` accepts directory names only, not paths.**

### Analysis budget

`max_work` is a deterministic logical unit budget covering source discovery,
lexing, parsing, resolution, and runtime enrichment. When exhausted,
`analysis_budget_exceeded` is raised **before any graph is published**; the
previous valid snapshot stays intact. The default (1,000,000) supports roughly
a few hundred KB of dense source. Raise it for larger projects:

```bash
mql5kg index ./MQL5/Experts --max-work 5000000 -o graph.json
```

Valid range: `1` … `10,000,000`.

## Query bounds (shared across CLI, HTTP, MCP, kernel)

| Parameter | Default | Range | Meaning |
|-----------|---------|-------|---------|
| `max_depth` | 1–3 | 0–5 | Traversal depth limit |
| `max_items` | 30–2000 | 1–2000 | Max result items |
| `max_paths` | 3 | 1–20 | Max paths returned by `trace` |
| `max_expansions` | 10000 | 1–100000 | Max graph expansions a traversal may make |
| `context_units` | 100 | 1–10000 | Context package budget (structural records) |

## Reference corpus

Configured at build time through `BuildRequest` fields: `input_dir`,
`output_dir`, optional `sources_path`, `max_pdf_bytes` (default 512 MiB),
`max_pages_per_source` (default 20000), and `max_pages_per_section` (default
32). See `docs/reference-corpus.md`.

## Graphify overlay

Configured through `GraphifyRequest`: `executable`, `backend`,
`processing_boundary`, `allow_remote`, `model`, `timeout_seconds`,
`max_concurrency`. See `docs/graphify.md`.

## Output files

| Artifact | How produced |
|----------|--------------|
| Graph (`graph.json`) | `mql5kg index ROOT -o graph.json` (default) |
| GraphML / markdown | `mql5kg export GRAPH --format graphml|markdown -o OUT` |
| Reference corpus | `build_reference_corpus(BuildRequest(...))` |
| Token benchmark report | `python -m mql5_kg.benchmarks.token_efficiency ROOT --symbol S --output PATH` |

Graph output paths are never committed (see `.gitignore`).

## Environment

- Tests: `pip install -e ".[dev]"`
- MCP requires `mcp` (`pip install -e ".[mcp]"`); reference build requires
  `pypdf`, `pypdfium2` (`pip install -e ".[reference]"`).
- The core has **no required third-party dependencies**.