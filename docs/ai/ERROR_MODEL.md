# ERROR MODEL (AI Audience)

Errors are machine-readable, never raw stack traces. Three levels:

1. **Intelligence errors** — `intelligence/errors.py` (kernel).
2. **Adapter errors** — `adapters/mcp/service.py` `AdapterError`.
3. **Analysis errors** — `analysis_budget.py` `AnalysisBudgetExceeded`,
   reference/compiler errors.

## IntelligenceError

```json
{
  "error": {
    "contract_version": "1.0.0",
    "category": "request | compatibility | state",
    "code": "...",
    "message": "...",
    "field": "...",
    "retryable": false
  }
}
```

### Codes

| Code | Category | Meaning |
|------|----------|---------|
| `invalid_parameter` | request | a bound/field is out of range or malformed |
| `invalid_request` | request | unknown field, missing shape, etc. |
| `missing_target` | request | operation needs a target (or two for `path`) |
| `unsupported_operation` | compatibility | unknown `operation` |
| `unsupported_contract_version` | compatibility | wrong contract major |
| `unsupported_graph_schema` | compatibility | graph schema not supported |
| `graph_identity_mismatch` | state | `expected_source_fingerprint` ≠ snapshot (retryable) |

## AdapterError (MCP/CLI HTTP)

```
{ "error": { "code", "message", "details": {} } }
```

| Code | Meaning |
|------|---------|
| `invalid_project_root` | root missing / not a directory |
| `invalid_tool_arguments` | malformed args (e.g. `excluded` path) |
| `project_not_indexed` | query before `index_project` |
| `analysis_budget_exceeded` | `max_work` exhausted (details has `recommended_actions`) |
| `analysis_failed` | unexpected analysis failure |
| `intelligence_error` | wraps an IntelligenceError in `details.intelligence_error` |
| `reference_not_loaded` | reference query before corpus load |
| `reference_snapshot_stale` | `expected_corpus_fingerprint` mismatch |

## AnalysisBudgetExceeded

Raised **before** publishing; previous valid graph stays intact. Details:
`phase`, `work_used`, `work_limit`, `budget_kind`,
`recommended_actions` (narrow root / narrow includes / increase max_work).

## Reference errors (`reference/models.py`)

`ReferenceError { code, message, details }`: `invalid_reference_root`,
`invalid_source_manifest`, `invalid_reference_source`, `invalid_reference_query`,
`reference_not_built`, `reference_snapshot_incomplete`, `reference_integrity_failed`,
`reference_limit_exceeded`, `reference_section_not_found`,
`reference_dependency_missing`, `reference_build_failed`,
`reference_source_changed`.

## Rules

- Never leak internal tracebacks through API/MCP responses.
- Adapters translate expected errors; unexpected failures become generic
  machine-readable codes with a safe reason.
- `retryable` is honored: a client may retry `graph_identity_mismatch` after
  re-indexing.
- Add new codes to this file when you add failure modes.