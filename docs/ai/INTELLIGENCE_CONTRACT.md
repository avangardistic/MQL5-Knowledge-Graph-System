# INTELLIGENCE CONTRACT (AI Audience)

Authoritative contract: `mql5_kg/intelligence/models.py` (v1.0.0,
`CONTRACT_VERSION`). The **IntelligenceKernel** (`intelligence/kernel.py`)
owns all semantic queries; adapters project through it.

Read `ERROR_MODEL.md` for the error envelope. Read `CONTEXT_ENGINE.md` for
the package algorithm.

## Request

```json
{
  "contract_version": "1.0.0",
  "operation": "query | context | impact | path | context_package | diagnostics",
  "targets": [{"value": "Name", "kind": null}],
  "direction": "incoming | outgoing | both",
  "relationship_types": ["calls"],
  "node_kinds": [],
  "bounds": {
    "max_depth": 1, "max_items": 30, "max_paths": 3,
    "max_expansions": 10000, "context_units": 100
  },
  "expected_source_fingerprint": null,
  "client_request_id": null
}
```

Validation: unknown fields rejected; `targets` ≤ 2 (2 only for `path`);
`direction`, `relationship_types`, `node_kinds`, `bounds` validated. Bounds:
`max_depth` 0–5, `max_items` 1–2000, `max_paths` 1–20, `max_expansions`
1–100000, `context_units` 1–10000. If `expected_source_fingerprint` is set and
≠ active snapshot → `graph_identity_mismatch` (Invariant 6).

## Operations

### `query`
Resolve one symbol. Result: `resolution` (matched/ambiguous/no_match),
`nodes` (bounded by `max_items`), `completion`.

### `context`
Bounded neighborhood around target(s). Direction filters (`incoming` =
callers/references, `outgoing` = callees/dependencies, `both`).
`relationship_types` filters edge kinds. Returns `nodes` + `relationships`
with evidence.

### `impact`
Upstream impact of changing a target: traverse `incoming` edges bounded by
`max_depth`/`max_items`. Returns distance-classified nodes.

### `path`
Directed paths between two targets (`outgoing` by default). Returns `paths`
(ranked `DirectedPath` with per-hop evidence) plus the nodes on those paths
so adapters can render names. `max_depth`, `max_paths`.

### `context_package`
Budgeted deterministic package (see CONTEXT_ENGINE). Returns
`context_package` (items + omissions) + `completion`.

### `diagnostics`
Ordered graph diagnostics (no targets). Returns `diagnostics` bounded by
`max_items`.

## Result

```json
{
  "contract_version": "1.0.0",
  "operation": "...",
  "graph_identity": {"graph_schema_version": "1.0.0",
                     "source_fingerprint": "...", "snapshot_revision": 1},
  "request": {...},
  "resolution": [{"selector": {...}, "status": "matched|ambiguous|no_match",
                  "candidates": [{"node_id": "...", "match_rank": 0, ...}]}],
  "nodes": [ NodeSummary ...],
  "relationships": [ RelationshipResult {id, source, target, relationship,
                     evidence {origin, confidence, location}} ...],
  "paths": [ DirectedPath {rank, node_ids, hops[]} ...],
  "context_package": {...},
  "diagnostics": [ DiagnosticResult ...],
  "completion": {"search_complete": true, "truncated": false,
                 "reason": "complete|max_depth|max_items|max_paths|max_expansions|context_budget|no_match|not_connected",
                 "omitted_counts": {...}, "explored_nodes": n, "explored_edges": m}
}
```

`completion` truthfully reports truncation (invariant). Ambiguity is surfaced
in `resolution.status` and edge `resolution_status`.

## Determinism

Same request on the same snapshot ⇒ same result: deterministic resolution,
traversal order, path ranking (`evidence_first_v1`), item ranking, and
diagnostic ordering. No unordered hash iteration.

## Legacy projectors

`kernel.legacy_find_nodes`, `legacy_neighborhood`, `legacy_upstream_impact`
reuse the same immutable index for the compatibility `graphify` CLI, keeping
historical shapes (see `compat/`).

## Adding operations

Extend `SUPPORTED_OPERATIONS`, implement `_execute_<op>`, add request/result
shapes, bump version per `CHANGE_GUIDE.md`, and add kernel tests.