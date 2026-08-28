# CHANGE GUIDE (AI Audience)

How to change the graph schema, contracts, or public surfaces without breaking
clients. Versioning rules are the contract of this system.

## Versioned artifacts

| Artifact | Constant | Location |
|----------|----------|----------|
| Graph schema | `SCHEMA_VERSION = "1.0.0"` | `graph.py` |
| Intelligence contract | `CONTRACT_VERSION = "1.0.0"` | `intelligence/models.py` |
| Reference contract | `CONTRACT_VERSION = "1.0.0"` | `reference/models.py` |
| Package | `version = "2.0.0"` | `pyproject.toml` / `version.py` |

## Changing the graph schema

1. Update `graph.py` (fields, relationships, `SCHEMA_VERSION`).
2. Mirror in `to_dict`/`from_dict`; keep serialization deterministic and
   sorted.
3. Bump `SCHEMA_VERSION` (major for breaking shape; minor/patch for
   additive/compatible).
4. Update `docs/ai/GRAPH_SCHEMA.md` and this file.
5. Add round-trip tests (`test_snapshots.py`) + update golden fixtures.
6. Old snapshots are **not** auto-migrated; load rejects mismatched schema.

## Changing the intelligence contract

Public request/result shapes, `SUPPORTED_OPERATIONS`, bounds, or completion
semantics affect every adapter:

1. Bump `CONTRACT_VERSION` major for breaking changes (`from_dict` rejects
   unknown major via `_version_major`).
2. Backward-incompatible request shapes fail fast with
   `unsupported_contract_version` / `invalid_request`.
3. Add compatibility path or explicit new version; do not silently change
   meaning of an existing field.
4. Update `docs/ai/INTELLIGENCE_CONTRACT.md` + `ERROR_MODEL.md` +
   `CHANGE_GUIDE.md`.
5. Update MCP tool schemas in `docs/ai/MCP_TOOLS.md` and any HTTP endpoints.

## Changing evidence/origin/relationship semantics

These are relied upon by AI clients. Add to the vocabulary only with tests and
doc updates:

- `evidence.py`: constants, `validate_origin`, policy.
- `docs/ai/EVIDENCE_MODEL.md`, `RELATIONSHIP_MODEL.md`, `SYMBOL_MODEL.md`.
- If adapters must understand it, that's a contract change → bump.

## Changing MCP tool schemas

- Additive (new tool / new optional arg with default) is backward-compatible;
  document in `MCP_TOOLS.md`.
- Removing or renaming a tool / required arg is breaking; preserve a legacy
  alias where practical (see the retained `get_symbol_context`,
  `resolve_includes`, `graphify` compat surfaces).

## Changing core modules (non-contract)

- Keep the invariants (`ARCHITECTURE_INVARIANTS.md`).
- Preserve determinism, budgets, and security boundaries.
- Add/adjust tests and update the relevant docs under `docs/` and `docs/ai/`.
- Run the full suite; run the CLI smoke; re-run the token benchmark if context
  behavior changed and record numbers in `docs/benchmarks/`.

## What must never change casually

- `IntelligenceRequest`/`Result` shapes without a version bump.
- The evidence vocabulary / origin semantics.
- The MCP/HTTP security boundary.
- Determinism guarantees and budget enforcement.
- Legacy entry points (`graphify`, `MQL5Parser`) without a documented break.