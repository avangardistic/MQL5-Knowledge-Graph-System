# Intelligence Kernel

The `IntelligenceKernel` (`mql5_kg/intelligence/kernel.py`) is the single
semantic boundary over one published canonical graph snapshot. **Every**
adapter — CLI, HTTP, MCP, legacy compatibility — projects through it. No
adapter implements graph semantics.

```
MCP / CLI / HTTP
      │
      ▼
IntelligenceKernel
      │
      ▼
    GraphIndex
      │
      ▼
     CodeGraph
```

## Operations

| Operation | What it does |
|-----------|--------------|
| `query` | Resolve a symbol by name/qualified name (exact, fuzzy, ambiguous, no-match) |
| `context` | Bounded neighborhood: callers, callees, references, dependencies |
| `impact` | Bounded upstream impact of changing a symbol (distance-classified) |
| `path` | Directed execution paths between two symbols with per-hop evidence |
| `context_package` | Deterministic budgeted context package with truthful omissions |
| `diagnostics` | Ordered graph diagnostics |

## Request / result contract

All operations speak one versioned contract (`contract_version: 1.0.0`):

```json
{
  "contract_version": "1.0.0",
  "operation": "context",
  "targets": [{"value": "ClosePosition", "kind": null}],
  "direction": "incoming",
  "bounds": {"max_depth": 1, "max_items": 200, "max_paths": 3,
             "max_expansions": 10000, "context_units": 100}
}
```

Results include `graph_identity` (schema version, source fingerprint,
snapshot revision), `resolution` status, bounded results, and a `completion`
record that truthfully reports truncation:

```json
"completion": {
  "search_complete": true,
  "truncated": true,
  "reason": "context_budget",
  "omitted_counts": {"relationships": 3}
}
```

## Determinism

- Symbol resolution, traversal ordering, search ordering, and path ranking
  are all deterministic.
- Graph and snapshot identity are fingerprints of source + configuration.
- No unordered hash iteration, filesystem order, or random IDs leak into
  results.

## Ambiguity

Resolution states are `matched`, `ambiguous`, and `no_match`. An ambiguous
call keeps all candidates and emits an `AMBIGUOUS_CALL` diagnostic — the
system never arbitrarily picks one (Invariant 4).

## Fingerprint consistency

A client may pass `expected_source_fingerprint`. If it does not match the
active snapshot, `graph_identity_mismatch` is returned instead of silently
mixing revisions (Invariant 6).

## Legacy projectors

The kernel also exposes `legacy_find_nodes`, `legacy_neighborhood`, and
`legacy_upstream_impact` used by the compatibility CLI (`graphify`). These
reuse the same immutable index while preserving historical shapes.

See `docs/ai/INTELLIGENCE_CONTRACT.md` for the authoritative contract
reference, and `docs/ai/ERROR_MODEL.md` for errors.
