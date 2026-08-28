# EXTENSION GUIDE (AI Audience)

How to extend the system safely: new relationships, parser constructs, MCP
tools. Always follow the invariants (`ARCHITECTURE_INVARIANTS.md`) and add
tests + docs.

## Adding a relationship type

1. Define the semantics first — **append to `docs/ai/RELATIONSHIP_MODEL.md`**:
   meaning, source/target kinds, origin, evidence, confidence, whether
   derived/reversible, false-positive risks, examples.
2. Emit it in the appropriate layer (resolver for resolution-time; runtime.py
   for event semantics; the overlay for `inferred`). Confidence per policy in
   `evidence.py` (add a constant if new).
3. Add tests asserting the origin, confidence, evidence, and false-positive
   guards (`test_resolver.py`, `test_runtime.py`).
4. If adapters filter on it, add it to the allowed relationship list (e.g.
   `legacy_upstream_impact` allowed set).

## Adding a parser construct

1. Handle it in `parser.py`, preserving locations and tolerance; emit
   diagnostics (never crash) on malformed variants.
2. Give it a declaration kind / node kind and document it in `docs/parser.md`,
   `docs/ai/SYMBOL_MODEL.md`, `docs/ai/GRAPH_SCHEMA.md`.
3. Add unit tests (small inline source) + a realistic fixture in
   `tests/fixtures/` + an adversarial case in `tests/fixtures/adversarial/`.
4. Ensure the token→function map stays near-linear (the O(functions ×
   bindings) bug is regression-tested).

## Adding an Intelligence operation

1. Extend `SUPPORTED_OPERATIONS` in `intelligence/models.py`; add the request
   fields and any result shape.
2. Implement `_execute_<op>` in `kernel.py` using the immutable index.
3. Keep determinism (no unordered hash iteration), bounds enforcement, and a
   truthful `completion`.
4. Add kernel tests (`test_intelligence.py`).
5. Optionally expose via CLI (`adapters/cli.py`), HTTP (`adapters/http.py`),
   and MCP (`adapters/mcp/`). Adapters only project — no duplicated semantics.

## Adding an MCP tool

1. Implement the behavior as a kernel/`ProjectSession` method (service layer).
2. Register the tool in `create_server` (`server.py`) with a clear name,
   typed schema, bounded args, and `_call` error projection.
3. Add a service-level test and, for end-to-end, a wire-protocol case in
   `TestMCPWireProtocol`.
4. Document in `docs/mcp.md` + `docs/ai/MCP_TOOLS.md`.

## Adding an evidence class or origin

1. Add the constant + membership in `evidence.py`; validate in `validate_origin`.
2. Update `docs/ai/EVIDENCE_MODEL.md`, `docs/ai/RELATIONSHIP_MODEL.md`.
3. Update the contract if adapters must understand it; follow
   `CHANGE_GUIDE.md` for versioning.

## Cross-cutting rules

- Add tests **for every** new behavior (unit + adversarial/security as
  applicable).
- Update human docs (`docs/`) and AI docs (`docs/ai/`) in the same change.
- Run `python -m pytest -q` before finishing.
- Never add a relationship "because it sounds useful" without defined
  semantics.