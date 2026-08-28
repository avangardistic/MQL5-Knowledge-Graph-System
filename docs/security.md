# Security

Security is a design invariant, not an afterthought. The highest-risk surface
is the MCP server, which must never become an unrestricted filesystem bridge
(Invariant 7). The same restrictions apply to the HTTP API.

## The security model

- **Adapter autonomy**: MCP/HTTP are read-only projections over an in-memory
  kernel. They do not write to disk, invoke external tools, access the
  network, or implement graph semantics.
- **Root confinement**: filesystem access is limited to the root passed to
  `index_project` plus explicit `include_roots`. `excluded` names prune
  discovery.
- **Bound every request**: tool inputs are typed and validated; results and
  graph traversals are bounded; budgets are enforced.
- **Machine-readable errors**: adapters return error envelopes, never stack
  traces.

## MCP restrictions

- Paths are resolved and confined to the project root. `..` traversal,
  absolute-path injection, and symlink escapes are rejected.
- `excluded` accepts directory names only (not paths) — `a/b`, `.`, and `..`
  are rejected.
- `include_roots` and the root must be existing directories.
- Requests are bounded (`max_items`, `max_depth`, `max_expansions`,
  `context_units`).
- `expected_source_fingerprint` guards against mixing snapshots: a mismatch
  returns an error instead of stale data.

## Threat model

| Threat | Mitigation |
|--------|------------|
| Path traversal (`../`) | Confined path resolution; traversal rejected |
| Absolute-path injection | Include/root must be resolved within project scope |
| Symlink escape | Symlinked dirs rejected where relevant (reference build) |
| Arbitrary filesystem reads | Only project root + include roots are scanned |
| Oversized requests | Bounded inputs and outputs |
| Unbounded graph traversal | `max_depth`, `max_expansions`, `context_units` |
| Mailformed MCP arguments | Typed schema validation on every tool |
| Invalid graph/revision IDs | Fingerprint + revision union validation |
| Corrupted graph files | Load-time validation; atomic saves |
| Credential/secret leakage | Restricted subprocess environment for Graphify; no secrets committed |
| Command injection | `shell=False`, explicit executable + arguments, timeout |
| Environment leakage | Graphify runs with a runtime-only + backend-only environment |

## External process security (Graphify)

- `shell=False` with an explicit executable and argument list.
- A timeout on every invocation.
- Output confined to an isolated staging directory.
- A restricted environment: only runtime variables and the selected backend's
  credential variables pass through; version probes run with runtime env only.
- `local` processing permits only the `ollama` backend and refuses
  non-loopback endpoints; `remote` processing requires explicit
  `allow_remote=True`.

## Error reporting

- Adapters return `{ "error": { "code", "message", "details" } }` envelopes.
- Internal exceptions never leak tracebacks through API/MCP responses.
- See `docs/ai/ERROR_MODEL.md`.

## Secrets policy

- No secrets, credentials, or local absolute paths are committed.
- Run `grep -r "password\|secret\|key\|token" --exclude-dir=.git --exclude-dir=__pycache__ .`
  before committing (expected hits: documentation words, env-var names — not values).

## Validated by tests

See `tests/test_security.py`: path traversal, absolute paths, budget limits,
fingerprint mismatch, restricted Graphify environment, and more.