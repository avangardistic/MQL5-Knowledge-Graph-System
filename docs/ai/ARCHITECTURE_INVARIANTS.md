# Architecture Invariants

These rules **must never be violated**. They are the contract the entire system is built
against. If a change conflicts with an invariant, the change is wrong — not the invariant.

## Invariant 1 — Canonical graph
There is exactly one authoritative `CodeGraph` per analysis. It owns entities, relationships,
diagnostics, evidence, metadata, schema version, graph identity, and source snapshot
information. No adapter maintains a parallel graph.

## Invariant 2 — Semantic core
Graph semantics live in the core (parser/resolver/kernel). CLI, HTTP, MCP and other adapters
must not independently implement graph semantics. The required call path is:

```text
MCP/CLI/HTTP → IntelligenceKernel → GraphIndex → CodeGraph
```

## Invariant 3 — Evidence
Every important relationship preserves its origin and evidence. Source-backed edges carry
`file:line:column` (and source fragment hash where appropriate); runtime edges carry their rule;
inferred edges carry source, model/backend, confidence, and inference status.

## Invariant 4 — Uncertainty
Ambiguous relationships remain ambiguous. Resolution states are exactly
`resolved | ambiguous | unresolved | inferred`. The system never converts ambiguity into
certainty and never invents confidence.

## Invariant 5 — Determinism
Same source + same configuration ⇒ deterministic graph identity, deterministic ordering,
deterministic query results, deterministic fingerprints. No unordered hash iteration, no
filesystem-order dependence, no random UUIDs in canonical output.

## Invariant 6 — Snapshot consistency
One request must never mix information from different graph revisions. Every intelligence
result carries `graph_identity` (schema + source fingerprint + revision). Clients may pin an
`expected_source_fingerprint`; a mismatch returns `graph_identity_mismatch` instead of serving
stale data.

## Invariant 7 — Security boundary
MCP and HTTP input must not arbitrarily expand filesystem access. Only the authorized project
root (plus explicitly configured include roots) is readable. `../` traversal, absolute-path
injection, symlink escapes, oversized requests, and unbounded traversal are rejected.

## Invariant 8 — Context budgets
AI context generation obeys explicit deterministic budgets (`context_units`). Relationships are
packed atomically with both endpoints; when the budget is exhausted the generator reports what
was omitted. A context package never exceeds its budget.

## Invariant 9 — Adapter independence
Removing MCP (or HTTP, or CLI) must not break the parser or intelligence functionality. The
core is fully usable offline through the Python API and CLI.

## Invariant 10 — Reference separation
Documentation/reference knowledge must never silently become code-graph truth. Reference
results carry `evidence_class: "reference_document"` plus citations and are queried through a
separate subsystem. Reference content never creates source-code relationships automatically.

## Invariant 11 — Semantic overlay separation
LLM/Graphify-derived inference remains explicitly classified as inference
(`origin: "inferred"`, evidence class `semantic_overlay_inference`), carries model/backend,
confidence, and the graph revision it was computed against, and is disposable. The core
functions without it.

## Invariant 12 — No partial publication
Failed analysis never replaces the last valid graph. Analysis builds a temporary graph,
validates it, builds and validates the index, then publishes atomically. A half-built graph is
never exposed.

## Invariant 13 — Analysis budget (derived from §31)
All analysis phases (discovery, lexing, parsing, resolution, runtime enrichment) consume a
deterministic work budget. Exhaustion fails safely with an explicit diagnostic; no partial graph
is published.

## Invariant 14 — Source locations are honest
Locations are `known`, `unknown`, `stale`, or `unavailable`. Line numbers are never fabricated.
If a location cannot be known, evidence states `location_missing` and the state is surfaced.

## Invariant 15 — No semantic duplication
There is no separate semantic implementation for CLI, HTTP, or MCP. All use the kernel.
