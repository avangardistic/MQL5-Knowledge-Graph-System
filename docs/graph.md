# Graph

The canonical `CodeGraph` (`mql5_kg/graph.py`) is the single authoritative
output of an analysis. It owns nodes, edges, diagnostics, metadata, schema
version, and the source fingerprint. It is serializable, deterministic, and
immutable-by-convention (snapshots are published atomically).

## Entities

### GraphNode

| Field | Meaning |
|-------|---------|
| `id` | Deterministic content-addressed identity (`stable_id`) |
| `kind` | `file`, `function`, `method`, `class`, `struct`, `enum`, `variable`, `input_variable`, `constant`, `property`, `macro`, `event_handler`, `imported_symbol`, `external_function`, `runtime` … |
| `name` | Unqualified name |
| `qualified_name` | Scope-qualified (`Engine::Start`, `file:SampleEA.mq5`) |
| `location` | `file`, `line`, `column` (+ optional end) |
| `attributes` | Typed extras (`return_type`, `parameter_count`, `external: True`, …) |

### GraphEdge

| Field | Meaning |
|-------|---------|
| `id` | Deterministic content-addressed identity |
| `source` / `target` | Node IDs |
| `relationship` | Typed relationship (`calls`, `includes`, `defines`, …) |
| `origin` | `extracted` \| `resolved` \| `runtime` \| `inferred` |
| `confidence` | 0.0–1.0 |
| `location` | Source evidence where available |
| `attributes` | e.g. `resolution_status`, `ambiguous`, `raw_target` |

See `docs/ai/GRAPH_SCHEMA.md` for the full schema and `docs/ai/RELATIONSHIP_MODEL.md`
for relationship semantics.

## Relationships

Canonical relationships include:

- `contains` / `defines` — structural containment and definition
- `includes` — file → included file (resolved to a file node when possible)
- `calls` — caller → callee (source-backed)
- `references` — symbol references
- `inherits` — class/struct inheritance
- `runtime_dispatches` — MetaTrader runtime → event handler
- `may_trigger_event` — operations that may fire a runtime event

Runtime relationships are **never** represented as source `calls`; the two
semantics remain distinct (Invariant 3 / 10 in
`docs/ai/ARCHITECTURE_INVARIANTS.md`).

## Evidence

Every important edge carries evidence: source location, origin, and
confidence. The system can always answer *"why does the graph believe this
relationship exists?"*. Evidence categories are:

- `code_graph` — extracted/resolved from source
- `reference_document` — from the reference corpus (never graph truth)
- `external_compiler_evidence` — correlated compiler logs
- `semantic_overlay_inference` — Graphify/LLM overlay (explicitly labeled)

See `docs/ai/EVIDENCE_MODEL.md`.

## Diagnostics

Diagnostics (`mql5_kg/diagnostics.py`) are machine-readable:

```
code            e.g. UNRESOLVED_INCLUDE
severity        error | warning | info
message
location        file, line, column
```

Categories include `parse_error`, `unresolved_include`, `unresolved_symbol`,
`ambiguous_symbol`, `unsupported_construct`, `graph_warning`,
`runtime_warning`, `configuration_error`. Diagnostics never corrupt graph
construction.

## Validation & snapshots

- `GraphSnapshot` (`mql5_kg/snapshots.py`) validates invariants — every edge
  endpoint exists, no impossible relationship type, every source-backed edge
  has evidence — before publishing.
- Failed analysis never replaces the last valid graph (Invariant 12).
- `CodeGraph.save` writes atomically; loading validates the file.

## Serialization

`graph.json` is a deterministic projection (sorted keys, content-addressed
IDs) — it is a serialization of the graph, never the semantic engine.
`docs/ai/GRAPH_SCHEMA.md` documents the shape and versioning rules.
