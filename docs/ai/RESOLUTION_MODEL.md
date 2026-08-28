# RESOLUTION MODEL (AI Audience)

Resolution (`mql5_kg/resolver.py`, scope model `scopes.py`) maps references
to canonical symbols. Resolution state is a first-class datum preserved on
edges; it is **never** collapsed into false certainty.

## States

| State | Constant | Meaning | Edge confidence |
|-------|----------|---------|-----------------|
| `resolved` | `STATE_RESOLVED` | a single best target; source-backed | 1.0 |
| `ambiguous` | `STATE_AMBIGUOUS` | multiple candidates; every candidate kept + reported | 0.65 |
| `unresolved` | `STATE_UNRESOLVED` | external/unknown target → `external_function` node | 0.5 |
| `inferred` | (overlay) | from an optional semantic overlay | overlay-set |

Resolution status appears on `calls` edges as `resolution_status` and mirrors
in `evidence.py` `RESOLUTION_STATES`.

## Include resolution

- Resolves `#include` against the including file's directory, the project
  root, then configured `include_roots`, all confined to approved roots
  (no traversal / absolute escapes).
- Missing include → unresolved `file` node (`unresolved: true`) +
  `RESOLVE001` diagnostic + confidence 0.35.
- Circular/deep include chains are handled safely (tested).

## Call resolution algorithm

1. Find all candidates with the called **name** across the repository.
2. Next prefer candidates whose name appears in the **caller's file**.
3. Prefer candidate **arity** (parameter count == argument count).
4. If a **receiver qualifier** (`obj.Method()`) is identified, prefer members
   of the resolved receiver type, then arity.
5. Otherwise prefer caller **same-scope** matches, then arity, then all.

The candidate set is chosen **by precedence, not by guessing**: if more than
one candidate remains, the call is `ambiguous` and every candidate becomes an
edge with `ambiguous: true`, plus an `AMBIGUOUS_CALL` (`RESOLVE002`)
diagnostic. Never arbitrarily pick one.

## Scope awareness

- `resolved` follows lexical scope: class-qualified calls resolve to class
  members over globals (tested by `test_class_method_scope_preference`).
- Queries can disambiguate via qualified names (`Engine::Start`) or `kind`.

## Unresolved external targets

A call with no candidate target creates/links an `external_function` node
`MQL5::{name}`, edge origin `extracted`, confidence 0.5, and one grouped
`RESOLVE003` info diagnostic (additional sites grouped).

## Rules

- Never convert `ambiguous` into `resolved`.
- Never convert `unresolved` into `resolved` unless new evidence (e.g.
  compiler evidence or a resolved include) justifies it.
- `inferred` edges must remain labeled inference (`EVIDENCE_MODEL.md`).