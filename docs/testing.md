# Testing

The project carries a serious, layered test suite. **208 tests pass.**

## Run the tests

```bash
pip install -e ".[dev]"        # pytest, pytest-asyncio, mcp
python -m pytest -q            # full suite
python -m pytest -v            # verbose (CI uses -v)
python -m pytest tests/test_parser.py        # a single file
python -m pytest -k "context"  # tests matching a name
```

`pyproject.toml` sets `asyncio_mode = "auto"` so async MCP tests run without
per-test markers.

## Test layout

```
tests/
├── conftest.py                    # shared fixtures (FIXTURES, ADVERSARIAL paths)
├── fixtures/                      # realistic MQL5 sources
│   ├── realistic_ea.mq5, IncludeTest.mqh, ...
│   └── adversarial/               # broken source, includes, imports
├── test_lexer.py, test_parser.py  # front-end
├── test_symbols.py, test_resolver.py, test_scopes.py
├── test_graph.py, test_snapshots.py, test_index.py
├── test_intelligence.py, test_context.py
├── test_runtime.py, test_diagnostics.py, test_analysis_budget.py
├── test_cli.py, test_http.py, test_mcp.py (wire protocol)
├── test_compat.py                 # legacy graphify / MQL5Parser facade
├── test_adversarial.py            # robustness against broken input
├── test_security.py               # path traversal, budget, fingerprint, env
├── test_incremental.py            # reuse / changed re-parse / determinism
├── test_regression.py             # previously-fixed bugs stay fixed
├── test_compiler_evidence.py      # compiler-log correlation
└── test_benchmark_token.py        # token-efficiency measurement
```

## Test categories

### Unit
Lexer, parser, graph, index, symbols, resolver, context, runtime,
diagnostics, budget — fast, pure, deterministic.

### Adversarial
`test_adversarial.py` and the `fixtures/adversarial/` set deliberately throw
malformed, partially edited, ambiguous, and include-heavy source at the
parser. The parser must fail **gracefully** (diagnostics, not crashes).

### Security
`test_security.py` asserts the MCP/HTTP boundaries: no traversal, no
absolute-path injection, bounded budgets, fingerprint-mismatch handling, a
restricted Graphify environment, and no shell usage.

### Invariant / property
Golden graph fixtures and round-trip serialization tests assert invariants:
every edge endpoint exists, ambiguity stays ambiguous, IDs are stable,
context budgets are never exceeded, `CodeGraph.save`/`load` round-trips.

### Wire protocol
`test_mcp.py` drives a real stdio MCP client against the server over the wire
(tools listed, index+query round-trip, context packages, error envelopes).

## Adding new tests

1. Mirror the existing structure: a `test_*.py` matching `tests/`, using
   fixtures from `tests/fixtures/` where relevant.
2. For parser behavior, prefer small inline source strings for unit tests and
   put realistic multi-construct sources in `fixtures/`.
3. For adversarial behavior, add a fixture to `tests/fixtures/adversarial/`
   and assert the parser emits appropriate diagnostics instead of crashing.
4. For MCP, test the service level (`ProjectSession`) and add a wire-protocol
   test in `TestMCPWireProtocol` for end-to-end coverage.
5. For security, add the attack case to `test_security.py`.
6. Run the full suite before finishing; never rely on a single-file run.

Run `python -m compileall -q mql5_kg` as a cheap syntax check before running
pytest.

## CI

`.github/workflows/ci.yml` runs the suite on Python 3.10, 3.11, and 3.12 on
every push/PR to `main`, plus a CLI smoke test. See `docs/development.md`.