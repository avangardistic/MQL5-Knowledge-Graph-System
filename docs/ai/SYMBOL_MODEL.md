# SYMBOL MODEL (AI Audience)

Canonical symbol model (`mql5_kg/symbols.py`). Define what a symbol is, its
identity, and its categories.

## What a symbol is

A symbol = a canonical node in the `CodeGraph` with a stable, deterministic
identity. Symbols exist for both declared code constructs and files.

## Identity rules

| Symbol | ID scheme |
|--------|-----------|
| Declared (function/method/class/…) | `symbol_id(kind, file, qualified_name, signature)` |
| File | `file_id(relative_path)` |
| External unresolved call target | `external_id(name)` → `qualifed "MQL5::{name}"`, kind `external_function` |
| Unresolved include | `stable_unresolved_file_id(target)` |

Identity is **content-addressed** (depends on kind + file + qualified name +
signature), so it is stable across runs and edits that don't change the
symbol's identity. Never derive identity from line numbers.

## Categories

| Category | Source | Notes |
|----------|--------|-------|
| `file` | discovery | `qualified_name` = relative path |
| `function` | parser | free function |
| `method` | parser | class/struct member |
| `constructor` | parser | name == owner |
| `destructor` | parser | `~Name` == owner |
| `event_handler` | parser | `OnInit`… `OnTick`, at global scope |
| `class` / `struct` / `enum` | parser | type ranges |
| `input_variable` | parser | `input`/`sinput` globals |
| `variable` / `constant` | parser | global bindings |
| `property` | parser | `#property` |
| `macro` | parser | `#define` |
| `imported_symbol` | parser | inside `#import "dll"` block (attributes carry `imported_from`) |
| `external_function` | resolver | unresolved call target |

## Qualified names

- Global: `Name`
- Members: `Owner::Name` (e.g. `Engine::Start`)
- Files: relative POSIX path (`RiskManager.mqh`)
- External: `MQL5::Name`

Attribute sets:
`signature`, `parameter_count`, `return_type` (functions/methods); `external`,
`unresolved` flags; `imported_from` for imports.

## Scope model (`scopes.py`)

Resolution prefers the correct lexical scope over repository-wide name
matching. Queries can pass a qualified name or `kind` to disambiguate.
Ambiguity is represented explicitly as a resolution state on edges
(`resolved` / `ambiguous` / `unresolved` / `inferred`) — it is never silently
collapsed (`RESOLUTION_MODEL.md`).