# MQL5 Knowledge Graph System — Audit Baseline

## Environment

- **Python**: 3.12.10 (Linux environment, not Windows 3.13 as specified)
- **pip**: 25.0.1
- **MCP SDK**: 1.11.0 (installed at `/usr/local/lib/python3.12/site-packages/mcp/__init__.py`)
- **OS**: Linux (containerized)
- **Repository commit**: 51df752 (main branch)
- **Working directory**: /workspace

## Repository Structure

```
/workspace/
├── README.md
├── graph.json (generated)
├── GRAPH_REPORT.md (generated)
├── mql5_kg/
│   ├── __init__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   └── graphify.py
│   ├── mcp_server/
│   │   ├── __init__.py
│   │   └── server.py
│   ├── parser/
│   │   ├── __init__.py
│   │   └── mql5_parser.py
│   └── storage/
│       ├── __init__.py
│       └── graph_storage.py
├── sample_mql5/
│   ├── SampleEA.mq5
│   └── RiskManager.mqh
└── tests/ (MISSING - no test directory exists)
```

## Commands Tested

### CLI Help
```bash
python -m mql5_kg.cli.graphify --help
```
**Result**: Works, but shows RuntimeWarning about module import order.

### Build Command
```bash
python -m mql5_kg.cli.graphify build sample_mql5 --report
```
**Result**: Works, generates graph.json and GRAPH_REPORT.md

### Query Commands
All query commands work:
- `query search "position"` ✓
- `query symbol OnTick` ✓
- `query impact OpenBuyOrder` ✓
- `query trace OnTick ModifyPositionSL` ✓
- `query file SampleEA.mq5` ✓
- `query includes SampleEA.mq5` ✓ (returns empty includes since SampleEA.mq5 has no #include)

### MCP Server
Not tested yet - requires graph.json to exist first.

## Exact Failures Identified

### 1. No Python Packaging (pyproject.toml missing)
The repository lacks proper Python packaging. Cannot install with `pip install -e .`.

### 2. No Test Suite
No `tests/` directory exists. No pytest configuration. No test fixtures.

### 3. Parser Issues - False Global Variables
The parser incorrectly identifies literals and keywords as global variables:
- `0` identified as `global_variable`
- `lots` identified as `global_variable` (it's a local variable)
- `false` identified as `global_variable`
- `true` identified as `global_variable`
- `currentTime` identified as `global_variable` (it's a local variable)

### 4. Incorrect CALLS Edges
The parser creates false CALLS edges from function bodies that scan too broadly:
- `CalculateLotSize` shown as calling `CanOpenPosition`, `IsDailyLimitReached`, etc. (incorrect - these are separate functions in the same file)
- The function body extraction uses a fixed 5000 character window which can bleed into other function definitions

### 5. Duplicate Edges
Multiple identical CALLS edges exist due to scanning approach without deduplication.

### 6. Missing Node Types
The sample MQL5 files don't exercise all node types:
- No `enum` or `enum_member`
- No `struct`
- No `class`
- No `input_variable` (the parser pattern for inputs is broken)
- No `define`

### 7. Input Variable Pattern Broken
Looking at the parser regex:
```python
self.pattern_input = re.compile(
    r'^\s*input\s+(\w+(?:\s*\[\s*\d+\s*\])?(?:\s*&)?)(?:\s+(\w+))?\s*;',
    re.MULTILINE
)
```
This pattern expects type then name, but MQL5 input syntax is `input double LotSize = 0.1;` - the pattern doesn't correctly capture this.

### 8. MCP Server API Compatibility Issue
The current MCP SDK (v1.11.0) uses decorators differently than implemented:
- Current code uses `@self.server.list_tools()` and `@self.server.call_tool()` as decorators
- Modern MCP SDK expects these to be used with async context managers or explicit registration

### 9. No tests/fixtures directory
No MQL5 test fixtures exist for comprehensive testing.

### 10. README Installation Instructions Incomplete
README says `pip install mcp` but doesn't mention installing the package itself.

## Root-Cause Hypotheses

1. **Parser Logic**: The `_extract_global_vars` method is too aggressive, matching any line that looks like a variable declaration without properly tracking scope (inside vs outside functions).

2. **Function Call Detection**: The `_build_relationships` method scans a fixed 5000-character window after function definition start, which can include other function definitions. It also doesn't filter out control flow keywords.

3. **Input Pattern**: The regex for input variables doesn't match the actual MQL5 syntax properly.

4. **MCP Integration**: The MCP SDK has evolved, and the decorator-based registration may need updating for proper async handler support.

5. **Packaging**: The project was developed as a standalone script collection without proper Python package structure.

## Next Steps

1. Create `pyproject.toml` for proper packaging
2. Create comprehensive MQL5 test fixtures
3. Fix parser logic for:
   - Global variable detection (scope awareness)
   - Function call detection (proper body extraction, keyword filtering)
   - Input variable pattern
4. Update MCP server for current SDK compatibility
5. Create test suite with pytest
6. Add graph integrity validation
7. Update README with accurate instructions
