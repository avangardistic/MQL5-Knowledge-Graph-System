# GRAPH SCHEMA (AI Audience)

The canonical `CodeGraph` (`mql5_kg/graph.py`). Current
`SCHEMA_VERSION = "1.0.0"`.

## Files

| File | Contents |
|------|----------|
| `graph.py` | `SCHEMA_VERSION`, `stable_id`, `SourceLocation`, `GraphNode`, `GraphEdge`, `CodeGraph` (save/load deterministic, atomic) |
| `snapshots.py` | `GraphSnapshot` (validate + publish immutably) |

## Identity

`stable_id(prefix, *parts)` is deterministic content addressing:
`sha1("\x1f".join(str(part) for part in parts))[:20]`, formatted `prefix:hex`.
Node/edge/declaration IDs are content-addressed so **same source + config ⇒
same IDs** (Invariant 5). Never use line numbers as identity.

Identity constructors (`symbols.py`): `symbol_id(kind, file, qualified_name,
signature)`, `file_id(relative_path)`, `external_id(name)`,
`stable_unresolved_file_id(target)` (`resolver.py`).

## SourceLocation

`{file, line, column, end_line?, end_column?}` (`to_dict` omits
absent end fields).

## GraphNode

| Field | Type | Notes |
|-------|------|-------|
| `id` | str | content-addressed |
| `kind` | str | see Node kinds |
| `name` | str | unqualified |
| `qualified_name` | str | scope-qualified, or relative path for files |
| `location` | SourceLocation\|None | where defined |
| `attributes` | dict | typed extras (hashable by `id`) |

### Node kinds

`file`, `function`, `method`, `constructor`, `destructor`, `event_handler`,
`class`, `struct`, `enum`, `input_variable`, `variable`, `constant`,
`property`, `macro`, `imported_symbol`, `external_function`, plus
`runtime` (overlay/runtime artifacts).

External unresolved call targets become `external_function` nodes with
`qualified_name = "MQL5::{name}"`.

## GraphEdge

| Field | Type | Notes |
|-------|------|-------|
| `id` | str | content-addressed |
| `source` / `target` | str | node IDs |
| `relationship` | str | typed relationship |
| `origin` | str | `extracted`\|`resolved`\|`runtime`\|`inferred` |
| `confidence` | float | 0.0–1.0 |
| `location` | SourceLocation\|None | evidence where available |
| `attributes` | dict | e.g. `resolution_status`, `ambiguous`, `argcount`, `raw_target` |

Edge construction validates `origin` and `confidence` (`validate_origin`,
`validate_confidence` in `evidence.py`).

### Relationship types

See `RELATIONSHIP_MODEL.md` for full semantics. Canonical set includes
`defines`, `contains`, `includes`, `calls`, `references`, `inherits`,
`runtime_dispatches`, `may_trigger_event`, `declares`.

## Diagnostics

`Diagnostic { code, severity, message, location? }`. Severities:
`error`, `warning`, `info`. Codes in `diagnostics.py`:
`LEX001`, `LEX002`, `PARSE001`, `RESOLVE001` (unresolved include),
`RESOLVE002` (ambiguous call), `RESOLVE003` (unresolved call),
`SOURCE001` (decode recovery), `GRAPH001` (validation).

## Metadata

`code_graph.metadata` holds `root`, `source_fingerprint`, `file_count`,
`tool_version`, `node_count`, `edge_count`, `diagnostic_count`. The
`source_fingerprint` is a deterministic SHA-256 over sorted relative paths +
content — it identifies the analysis input.

## Serialization

`CodeGraph.to_json()` / `save(path)` is a **deterministic projection**
(sorted keys, content-addressed IDs, one trailing LF) — it is serialization,
**never** the semantic engine. `load(path)` validates structure.
Graph saves are atomic (temp + `os.replace`).

## Versioning rules

- Changing the schema (fields, relationships, meaning) requires bumping
  `SCHEMA_VERSION` and following `CHANGE_GUIDE.md`.
- A new major version is a new shape; old snapshots are not auto-migrated.
- Always add round-trip tests (`test_snapshots.py`) on schema change.