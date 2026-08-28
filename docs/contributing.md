# Contributing

Contributions are welcome. This document sets the standards every change must
meet. Read `AGENTS.md` and `docs/ai/ARCHITECTURE_INVARIANTS.md` first — they
state the rules that cannot be broken casually.

## Ground rules

- **Correctness over convenience.** Do not degrade parser tolerance, evidence,
  or determinism to make a change smaller.
- **Evidence over apparent completeness.** Never invent certainty for an
  ambiguous relationship.
- **An adapter is a projection.** Add semantics to the core (kernel/parser),
  never to CLI/HTTP/MCP.
- **Determinism.** No unordered hash iteration, no random IDs, no
  filesystem-order dependence in canonical results.
- **Standalone core.** The core uses only the stdlib. Optional features live
  behind the `mcp` / `reference` extras.

## Development setup

```bash
pip install -e ".[dev]"
python -m compileall -q mql5_kg
python -m pytest -q
```

See `docs/development.md`.

## Making a change

1. **Pick a small, focused change.** Prefer a clean fix over layering hacks.
2. **Write a test first** (or update an existing one) that fails without your
   change and passes with it. Mirror the suite structure
   (`docs/testing.md`).
3. **Implement** the change, keeping code style consistent (typed annotations,
   module docstrings, `stable_id`, canonical JSON).
4. **Update docs** that your change touches (`docs/` for humans,
   `docs/ai/` for agents, `README.md` / `AGENTS.md` / `FINAL_REPORT.md` when
   behavior changes).
5. **Run the full suite** and the CLI smoke test:
   ```bash
   python -m pytest -q
   mql5kg index sample_mql5 -o /tmp/graph.json --json
   mql5kg trace /tmp/graph.json OnTick OrderSend
   ```
6. **Run the secret scan** before committing:
   ```bash
   grep -r "password\|secret\|key\|token" --exclude-dir=.git --exclude-dir=__pycache__ .
   ```
   (Expected hits are documentation words and env-var names, not values.)

## Changing contracts or graph schema

Public shapes (`IntelligenceRequest`/`Result`, `CodeGraph` schema, contract
versions, MCP tool schemas) change only with a version bump and a migration
note. Follow `docs/ai/CHANGE_GUIDE.md`. Add round-trip tests and update golden
fixtures and `docs/ai/GRAPH_SCHEMA.md`.

## Security-sensitive changes

MCP/HTTP security is non-negotiable. Any change to path handling, bounds,
budgets, or subprocess execution must:
- preserve root confinement, traversal rejection, and typed validation;
- add matching assertions in `tests/test_security.py`;
- be reviewed against `docs/ai/SECURITY_MODEL.md`.

## Documentation as first-class

- Documentation targets two audiences: humans (`docs/`) and AI agents
  (`docs/ai/`). Keep both accurate and in sync.
- Never claim unmeasured token savings; record benchmarks instead
  (`docs/benchmarking.md`).
- State limitations honestly in `FINAL_REPORT.md`.

## Pull request process

1. Branch off `main` with a descriptive name.
2. Keep the change focused; split unrelated work into separate PRs.
3. Describe the why (motivation) in the PR body, reference issues/PRs, and
   include test + benchmark results.
4. CI (.github/workflows/ci.yml) runs `pytest -v` and a CLI smoke test on
   Python 3.10/3.11/3.12; it must be green.
5. One approving review that checks standards adherence (invariants, security,
   docs, no secrets).

## License

MIT — by contributing you agree to license your contribution under the MIT
License (see `LICENSE`).