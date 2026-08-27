# MQL5 Knowledge Graph — Forensic Audit Baseline

## Audit Metadata

| Item | Value |
|------|-------|
| Date | 2026-08-27 |
| Branch | fix/mql5-kg-forensic-repair |
| Python | 3.13.10 |
| MCP SDK | 2.1.1 |
| pytest | 9.1.1 |
| OS | Windows 11 Enterprise 10.0.22621 |

## Baseline State (before fixes)

- **Tests**: 0 tests existed (only fixture directory with 2 files)
- **`pytest -q`**: "no tests ran" (exit 5)
- **AttributeError**: `python -m mql5_kg.cli.graphify query search OnTick` crashed with `AttributeError: 'Server' object has no attribute 'list_tools'`
- **RuntimeWarning**: `RuntimeWarning: 'mql5_kg.cli.graphify' found in sys.modules` on every CLI invocation
- **Function extraction**: Broken — `_extract_functions` guard `if return_type in _MQL5_KEYWORDS` erroneously skipped all functions with primitive return types (`int`, `void`, `double`, `bool`, `string`)
- **False CALLS edges**: `if(`, `for(`, `while(`, `switch(` were captured as function calls and stored as CALLS edges
- **Invalid symbols**: comment tokens, numeric literals, and boolean literals could become graph nodes

## Root Causes Identified

| # | Component | Root Cause |
|---|-----------|------------|
| 1 | CLI `__init__.py` | Eagerly imported `graphify` module at package import time, so when Python ran `python -m mql5_kg.cli.graphify` it found the module already in sys.modules |
| 2 | MCP server | Used MCP SDK v1 decorator API (`@server.list_tools()`, `@server.call_tool()`) which was removed in SDK v2.x |
| 3 | Parser — return types | `_MQL5_KEYWORDS` included type keywords (`int`, `void`, `double`, `bool`) AND the function extractor skipped any function whose return type was in that set |
| 4 | Parser — false CALLS | `pattern_function_call` matched `\b(\w+)\s*\(` capturing everything before `(`, with no keyword exclusion |
| 5 | Parser — invalid symbols | No stripping of comments/strings before extraction; no guard against numeric/boolean tokens |

## Files Changed

| File | Change |
|------|--------|
| `mql5_kg/cli/__init__.py` | Lazy import via `__getattr__` to prevent module pre-loading |
| `mql5_kg/mcp_server/server.py` | Rewrote `_register_tools()` to use MCP SDK v2 `add_request_handler` API |
| `mql5_kg/parser/mql5_parser.py` | Split keywords into `_CONTROL_FLOW_KEYWORDS` vs `_MQL5_KEYWORDS`; added `_strip_comments_and_strings()`; fixed return type capture (GROUP 1 of pattern); fixed CALLS keyword filter |

## Tests Added

| File | Tests |
|------|-------|
| `tests/test_parser.py` | 20 tests — false CALLS, symbol extraction, return types, graph integrity |
| `tests/test_graph.py` | 6 tests — storage save/load/report, graph integrity after build |
| `tests/test_cli.py` | 13 tests — build command, all 6 query commands, no RuntimeWarning/AttributeError |
| `tests/test_mcp.py` | 11 tests — MCP init, 6 tool calls, async dispatch |
| `tests/test_integration.py` | 12 tests — end-to-end: parse → graph → CLI → MCP |

## Fixtures Added

| File | Purpose |
|------|---------|
| `tests/fixtures/control_flow_test.mq5` | Exercises if/for/while/switch — confirms no false CALLS |
| `tests/fixtures/return_type_test.mq5` | double/int/bool/string/void functions |
| `tests/fixtures/realistic_ea.mq5` | Full EA for end-to-end integration testing |

## Final Test Results

```
70 passed in 30.88s
```

## Validation Summary

| Component | Before | After |
|-----------|--------|-------|
| Tests | 0 | 70 |
| CLI RuntimeWarning | Present | Gone |
| CLI AttributeError | Present | Gone |
| Function extraction | Broken (0 functions) | Working |
| Return types | Wrong (default void) | Correct |
| False CALLS (if/for/while/switch) | Present | Fixed |
| Invalid symbol names | Possible | Prevented |
| MCP SDK compatibility | SDK v1 only | SDK v2.1.1 |
| Python 3.13.10 | Untested | 70/70 pass |
