# SECURITY MODEL (AI Audience)

Security is non-negotiable (Invariant 7). This is the threat model an agent
must respect when modifying adapters or external-process code.

## Core boundaries

- **Adapters are read-only projections.** They do not write to disk, invoke
  tools, or add filesystem access.
- **Root confinement.** Filesystem access = `index_project` root +
  explicit `include_roots`. `excluded` prunes discovery within those roots.
- **Bounded everything.** Inputs, results, and graph traversals are bounded;
  budgets are enforced.
- **No secrets.** No credential leakage; a restricted subprocess environment
  for external tools.

## MCP/HTTP restrictions

- Paths resolved + confined to the project root; `..` traversal, absolute-path
  injection, and symlink escapes rejected.
- `excluded` validated as directory names only (`a/b`, `.`, `..` rejected).
- Tool args typed + validated; `expected_source_fingerprint` guards snapshot
  consistency.
- Errors are envelopes, never tracebacks.

## External process (Graphify)

- `shell=False`, explicit executable + args, timeout.
- Restricted environment: runtime vars + selected backend credential vars only;
  version probes run without backend credentials.
- Output isolated to a staging dir; overlay output must be separate from the
  authoritative corpus.
- `local` boundary = ollama-only + refuses non-loopback endpoints; `remote`
  requires explicit `allow_remote`.

## Reference corpus

- All paths confined (`confined_relative_path`); symlinked inputs rejected.
- Size limits enforced; hashes verified; publication atomic.

## Threat → mitigation (see docs/security.md)

path traversal, absolute injection, symlink escape, arbitrary reads, oversized
requests, unbounded traversal, malformed args, invalid revision IDs, corrupted
graph files, cred leakage, command injection, env leakage — each has a
mitigation.

## What an agent must preserve

Any change to path handling, bounds, budgets, or subprocess execution must
keep: root confinement, traversal rejection, typed validation, and must add
assertions in `tests/test_security.py`. See `docs/security.md` for the full
model and `tests/test_security.py` for the enforced checks.