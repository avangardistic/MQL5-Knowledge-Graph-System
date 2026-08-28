# Context Engine

The context engine (`mql5_kg/context/engine.py`) is the system's
token-efficiency core. It generates compact, AI-oriented structural context
under an explicit, deterministic budget.

## The problem

An AI agent asked "what does this change affect?" does not need the whole
source tree — it needs the symbol's definition, its callers, callees, and
dependencies, with evidence, bounded to a budget. The context engine produces
exactly that, and **truthfully reports what was omitted** when the budget ran
out.

## Units

A `context_units` budget counts structural records:

- a target node summary = 1 unit
- an endpoint node summary = 1 unit
- a relationship (packed atomically with its endpoint summaries) = 1 +
  missing-endpoint units
- a diagnostic = 1 unit

Relationships are **always packed atomically** — never a half relationship
with missing endpoints.

## Ranking

Items are ranked deterministically:

1. target nodes (always included first)
2. relationships by tier (1-hop before deeper), distance, evidence origin
   (source-backed before inferred), then confidence
3. local diagnostics before global diagnostics

## Example

`mql5kg context graph.json CloseBasket --budget 100 --json` returns a package
like:

```json
"context_package": {
  "budget_kind": "structural_record_v1",
  "budget_limit": 100,
  "budget_used": 92,
  "items": [
    {"rank": 1, "category": "target", "summary": {"kind": "function",
     "qualified_name": "CloseBasket", ...}},
    {"rank": 2, "category": "relationship",
     "summary": {"relationship": "calls", "source": "...", "target": "..."},
     "evidence": {"origin": "resolved", "confidence": 1.0,
                  "location": {"file": "GridEA.mq5", "line": 184}}}
  ],
  "omissions": [{"category": "relationships", "count": 18},
                {"category": "nodes", "count": 7}]
}
```

The `completion` record explains truncation:

```
completion: {"search_complete": true, "truncated": true,
             "reason": "context_budget", "omitted_counts": {...}}
```

## Token efficiency

The benchmark (`docs/benchmarking.md`) measures — rather than claims —
how much smaller a context package is than raw source for representative
repositories. It compares three approaches:

- **A**: entire repository source
- **B**: only the files that define the symbol
- **C**: bounded graph context package (+ targeted definition window)

Measurements record bytes, estimated tokens (`chars / 4`), and latency, and
are stored under `docs/benchmarks/`.

## Guarantees

- The budget is never exceeded (invariant tested).
- Omissions are always reported — the engine never pretends the graph is
  complete.
- Ordering is deterministic across runs and platforms.
- The engine reads only the immutable `GraphIndex`; it never mutates the
  canonical graph.
