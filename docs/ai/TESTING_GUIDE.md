# TESTING GUIDE (AI Audience)

How to test, what the suite covers, and how to add tests.

## Run

```bash
pip install -e ".[dev]"
python -m compileall -q mql5_kg
python -m pytest -q
python -m pytest -v            # CI uses -v
```

## What the suite covers (197 tests)

- **Unit**: lexer, parser, symbols, resolver, graph, snapshots, index,
  intelligence, context, runtime, diagnostics, budget (`test_*.py`).
- **Adversarial**: `test_adversarial.py` + fixtures throw malformed/partially
  edited/ambiguous/include-heavy source at the parser; it must fail
  gracefully (diagnostics, no crashes).
- **Security**: `test_security.py` asserts the MCP/HTTP boundaries — path
  traversal, absolute injection, budget limits, fingerprint mismatch,
  restricted Graphify environment, no shell.
- **Invariant / property**: golden graphs, round-trip serialization, budget
  never exceeded, ambiguity stays ambiguous, IDs stable.
- **Wire protocol**: `test_mcp.py` drives a real stdio MCP client
  end-to-end.
- **Regression**: fixes stay fixed.
- **Compiler evidence**: `test_compiler_evidence.py`.
- **Benchmark**: `test_benchmark_token.py` runs the real token measurement.

## Adding tests

1. Choose the right file (or add a new `test_*.py`); mirror existing style.
2. Parser: prefer inline source for small unit tests; realistic multi-construct
   sources into `tests/fixtures/`; adversarial cases into
   `tests/fixtures/adversarial/`.
3. MCP: test `ProjectSession` at the service level; add a wire case in
   `TestMCPWireProtocol` for end-to-end.
4. Security: add the attack to `test_security.py`.
5. Run the full suite — never rely on a single-file pass.

## Adversarial strategy

The parser must survive, emitting diagnostics:

- same names / shadowing / nested scopes
- misleading comments and code-looking strings
- missing semicolons, unclosed blocks, partial declarations
- missing / deep / circular includes
- duplicate + overloaded symbols
- large files (linear time guard)

Assert diagnostics codes exist, not that the input "parses cleanly."

## Security tests to keep green

- `..` traversal and absolute paths rejected.
- `excluded` names-only validation.
- `max_work` budget exhaustion → `analysis_budget_exceeded`, no partial graph.
- `expected_source_fingerprint` mismatch → `graph_identity_mismatch`.
- Graphify subprocess: `shell=False`, restricted env, `--version` probe without
  credentials.
- Reference paths confined; symlinked inputs rejected.

## Golden graph fixtures

For input source, assert expected symbols, relationships, evidence, and
diagnostics. Round-trip: `CodeGraph.save` → `load` preserves identity
(`test_snapshots.py`).