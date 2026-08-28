# Discarded Components — What Was Removed and Why

| Component | Source | Reason discarded | Replacement |
|---|---|---|---|
| Regex-only `MQL5Parser` | Repo A | Cannot pair braces/parens, mis-attributes calls via 5000-char window, no scope/evidence/ambiguity | Tolerant structural parser + resolver (ported from Repo B) |
| Dict-shaped `graph.json` as the semantic engine | Repo A | Serialization must not be the database; no schema version, no deterministic IDs, no evidence | Canonical `CodeGraph` with schema version + atomic save |
| Adapter-level graph queries in MCP server | Repo A | Violates invariant "semantics live in the core" | `IntelligenceKernel` facade; MCP is a thin adapter |
| MCP SDK v1 handler registration | Repo A | Incompatible with installed MCP SDK (baseline failures) | FastMCP-based adapter over kernel sessions |
| `web/` React dashboard | Repo B | Out of scope for a self-contained Python repo; keeps the repo dependency-light and offline-first | Stdlib HTTP API adapter over the kernel |
| Repo B `.specify/`, `.agents/` speckit skills, plugin marketplace files | Repo B | Repository-governance/tooling metadata not part of the product | None (documented in Repo B only) |
| Repo B project journal + ADR series | Repo B | Internal process records; the final repo gets distilled AI/human docs instead | `docs/ai/*` + `docs/*` + `AGENTS.md` |
| `mql5_kg.egg-info/`, `__pycache__/`, `graph.json`, `GRAPH_REPORT.md` | Repo A working tree | Generated/build artifacts must not be committed | `.gitignore` entries; regenerated on demand |
| `graphify` command names | Repo A (renamed) | New CLI surface per §39 (`mql5kg index|search|symbol|…`) | Legacy names preserved via compat adapter |
| Repo B `ANALYSIS.md` large-file budget analysis | Repo B | Problem analysis of an already-fixed bug; the fix (O(1) token→function map) is integrated | Documented in `docs/architecture.md` performance notes |

## Not discarded but isolated

- Reference corpus (optional `[reference]` extra; never auto-creates graph relationships).
- Graphify semantic overlay (optional; `shell=False`; always labeled `semantic_overlay_inference`).
- Compiler-evidence correlation (read-only; never mutates the canonical graph).
