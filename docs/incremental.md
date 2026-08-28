# Incremental Indexing

Incremental indexing re-indexes a project faster by **reusing the parsed
result of every file whose bytes have not changed**, while remaining **fully
correct** — the rebuilt graph is identical to a full rebuild from the same
source.

## Why it is sound

The `CodeGraph` is built in two stages:

1. **Parse** each file → `ParseResult` (declarations, call sites, includes,
   diagnostics).
2. **Resolve** the whole repository from those `ParseResult`s (`build_graph`):
   includes, scope-aware calls, ambiguity, runtime enrichment.

Incremental indexing only avoids repeating stage 1 for unchanged files. Stage 2
(counted the "resolution" pass) **always runs over the full combined set of
ParseResults**, exactly as a full build does. Because resolution is
deterministic and sees every declaration/include/call site, a changed overload,
renamed symbol, or new header symbol resolves correctly for **all** callers —
even callers in files that were not re-parsed. This is the property that makes
partial-parsing safe (verified by tests that prove
`incremental_result == full_rebuild_result`).

## How it works

- A **`FileCache`** (persisted JSON, default `<output>.cache.json`) maps each
  file's content SHA-256 to its serialized `ParseResult` (versioned, compact).
- On each run the current source is hashed and diffed against the cache:
  - **unchanged** → load the serialized `ParseResult` (no re-lex, no re-parse);
  - **changed / added** → parse fresh and replace the cache entry;
  - **removed** → drop the cache entry.
- The full resolution pass then rebuilds the canonical graph from the combined
  ParseResults.
- The graph and cache are persisted **atomically together** only after a valid
  graph is produced (Invariant 12); a failed run leaves the previous artifacts
  intact.

## Modes

| Mode | When | Meaning |
|------|------|---------|
| `full` | no compatible cache, config changed, or cache corrupt/missing | Full rebuild, cache (re)populated |
| `incremental` | cache valid and at least one file changed/added/removed | Only changed files re-parsed; resolution runs fully |
| `reuse` | every file unchanged | All files reused; resolution runs fully (no-op change) |

The cache is bound to the analysis **configuration** (root, include roots,
excluded names, cache schema). Changing any of them invalidates the cache and
triggers a safe `full` rebuild.

## Usage

```bash
# First run: full build, populates graph.cache.json
mql5kg index ./MQL5/Experts --incremental -o graph.json

# Later runs reuse unchanged files
mql5kg index ./MQL5/Experts --incremental -o graph.json

# Custom cache path
mql5kg index ./MQL5/Experts --incremental -o graph.json --cache /path/cache.json
```

`--json` reports the outcome:

```json
{
  "mode": "incremental",
  "reused_files": 12,
  "changed_files": ["RiskManager.mqh"],
  "removed_files": [],
  "nodes": 412,
  "edges": 903
}
```

## Python API

```python
from mql5_kg import incremental_analysis, persist_incremental
from pathlib import Path

result, cache = incremental_analysis("project", cache_path=Path("graph.cache.json"))
# result.graph is a fully resolved, validated CodeGraph; result.mode tells
# whether it was incremental or a fallback full build.
persist_incremental(result, cache, graph_path=Path("graph.json"), cache_path=Path("graph.cache.json"))
```

## MCP note

The MCP server intentionally does **not** use a disk cache: it is a read-only,
no-disk-write adapter (see `docs/security.md`). It already avoids redundant work
in-memory by reusing a loaded snapshot when the source fingerprint is unchanged
(`index_project` returns `"reused": true`).

## What is NOT incremental

Resolution — the repository-wide include/call/scope pass — runs in full on every
incremental build. This is a deliberate correctness choice: partial resolution
of a call graph is unsafe (a single rename in one file can change what an
unrelated file calls) and would violate the determinism/correctness invariants.
The performance win is in skimping the expensive lex + parse + call-site
extraction stage for unchanged files, which dominates on large codebases.

## Safety & fallbacks

- A missing, truncated, or corrupt cache file → `mode: full` (never a bad graph).
- A single corrupt record → that file is re-parsed fresh.
- An incompatible cache schema → full rebuild.
- No cache path given at the API level → behaves like `analyze_repository`
  (full build) and returns an empty cache.

## Tests

`tests/test_incremental.py` covers reuse, changed re-parse, add/remove, disk
persistence, corrupt-cache fallback, config invalidation, the ripple of a
header change onto unchanged callers, and the central property that an
incremental build equals a full rebuild.