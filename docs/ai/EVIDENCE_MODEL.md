# EVIDENCE MODEL (AI Audience)

Authoritative vocabulary: `mql5_kg/evidence.py`.

## Evidence classes — what produced the evidence

| Class | Value | Meaning |
|-------|-------|---------|
| `code_graph` | `CODE_GRAPH` | derived from static source analysis |
| `reference_document` | `REFERENCE_DOCUMENT` | from the optional reference corpus |
| `external_compiler_evidence` | `EXTERNAL_COMPILER_EVIDENCE` | from operator-supplied compiler logs |
| `semantic_overlay_inference` | `SEMANTIC_OVERLAY_INFERENCE` | from an optional LLM/Graphify overlay |

`reference_document` and `semantic_overlay_inference` must **never** become
canonical graph truth (Invariants 10, 11).

## Relationship origins — how a relationship was produced

| Origin | Meaning |
|--------|---------|
| `extracted` | directly observed in source (e.g. a call-site token) |
| `resolved` | produced by repository-wide resolution (includes, calls) |
| `runtime` | runtime/event semantics not visible as source calls |
| `inferred` | from an optional semantic overlay; never canonical truth |

`validate_origin` rejects unknown origins at edge construction.

## Confidence

Real-valued in `[0, 1]`. See `RELATIONSHIP_MODEL.md` for per-relationship
normative confidence policy. `validate_confidence` at edge construction.

## Evidence reference (kernel)

The kernel returns `EvidenceReference { subject_id, origin, confidence,
location?, state, state_reason }` for each relationship/diagnostic.

Evidence states (`EVIDENCE_STATES`):

```
available   source file is present at the recorded location
stale       recorded location no longer matches the current source
unavailable source file/location unavailable to this process
unknown     probe not configured / location missing
not_applicable  no source location applies (runtime, inferred)
```

## Provenance — explaining "why does the graph believe this?"

For source-backed edges, evidence = `location {file, line, column}` +
`origin`. For runtime edges, evidence = the triggering runtime rule +
`origin: "runtime"`. For inferred edges, evidence = producer, backend,
fingerprints, confidence, and `origin: "inferred"` + `evidence_class:
"semantic_overlay_inference"`.

## Rules

- Never silently upgrade origin or confidence.
- Every source-backed edge must have location evidence (invariant tested).
- Adapters surface evidence; they never invent it.