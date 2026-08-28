# CONTEXT ENGINE (AI Audience)

`mql5_kg/context/engine.py`. Produces compact, deterministic AI context under
an explicit unit budget. It packs structural records **atomically** and
**truthfully reports omissions**.

## Budget semantics

`context_units` counts structural records:

- target node summary: 1 unit
- endpoint node summary: 1 unit
- relationship: 1 unit **+ 1 unit per missing endpoint node** (packed atomically)
- diagnostic: 1 unit

A relationship is never emitted with a missing endpoint summary.

## Traversal

From the target node(s), BFS outward in the requested `direction`, bounded by
`bounds.max_depth` and `bounds.max_expansions`. Only edges whose endpoints are
both within explored distances are eligible for packing.

## Ranking priority (deterministic)

1. **target nodes** first.
2. **relationships** by:
   - tier (1-hop before deeper),
   - distance,
   - evidence origin penalty (source-backed before inferred),
   - confidence (descending: high evidence first),
   - edge id tiebreak.
3. **diagnostics**: local-to-target before global; severity (`error` before
   `warning` before `info`).

## Selection pass

Walk ranked candidates; stop when remaining budget is exhausted. Every emitted
item increments `budget_used`. `budget_used` never exceeds `budget_limit`.

## Omission reporting (honesty required)

The package includes `omissions: [{category, count}]`:

| category | meaning |
|----------|---------|
| `nodes` | eligible nodes not packed |
| `relationships` | eligible edges not packed |
| `diagnostics` | eligible diagnostics not packed |
| `ambiguity_alternatives` | extra target candidates omitted |
| `search_space` | (count `null`) traversal was cut by `max_expansions`/`max_depth` |

`completion.reason` ∈ `complete` | `no_match` | `max_depth` | `max_expansions`
| `context_budget`. Truncation is always surfaced — the engine never pretends
the graph is complete.

## Output

```json
"context_package": {
  "budget_kind": "structural_record_v1",
  "budget_limit": 100, "budget_used": 92,
  "items": [
    {"rank":1,"category":"target","distance":0,"cost_units":1,
     "summary": {...}, "evidence": null},
    {"rank":2,"category":"relationship","distance":1,"subject_id":"edge:...",
     "summary": {"id":..., "source":..., "target":..., "relationship":"calls"},
     "evidence": {"origin":"resolved","confidence":1.0,
                  "location":{"file":"...","line":184}}}
  ],
  "omissions": [{"category":"relationships","count":18},{"category":"nodes","count":7}]
}
```

## Guarantees

- `budget_used <= budget_limit` (invariant-tested).
- Atomic relationship packing; no partial fragments.
- Deterministic ranking and ordering.
- Read-only over the immutable `GraphIndex`; never mutates the canonical graph.