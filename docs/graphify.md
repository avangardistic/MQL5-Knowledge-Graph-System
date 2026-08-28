# Graphify Semantic Overlay

Graphify is an **optional** external tool that can build a semantic overlay on
top of a reference corpus. It is a self-contained subsystem
(`mql5_kg/reference/graphify_adapter.py`) that never becomes canonical graph
truth (Invariant 11). The core parser, intelligence kernel, and MCP all work
without Graphify installed.

## Conceptual model

```
Canonical Static Graph        ReferenceCorpus
        +                        |
        └──────────── Optional Semantic Overlay (Graphify)
                                 │  evidence_class: "semantic_overlay_inference"
                                 │  producer (name+version), backend
                                 │  corpus_fingerprint, overlay_fingerprint
                                 │  local or remote (explicit authority)
                                 ▼
                           Disposable overlay  (never graph truth)
```

## What the adapter does

`build_graphify_overlay(GraphifyRequest, runner=subprocess.run)`
(`mql5_kg/reference/graphify_adapter.py`):

1. Requires an explicit `GraphifyRequest` with:
   - `executable` — the graphify command/path
   - `backend` — `gemini` | `kimi` | `claude` | `openai` | `deepseek` | `ollama`
   - `processing_boundary` — `local` or `remote`
   - `allow_remote` — must be `True` for remote processing (explicit authority)
   - optional `model`, `timeout_seconds`, `max_concurrency`
2. Validates the request and the overlay output directory is separate from the
   corpus root.
3. Probes the Graphify version (requires `>=0.9.0,<1.0.0`).
4. Runs `graphify extract <corpus documents> --out <staging> --backend ...` over
   the reference corpus documents.
5. Validates Graphify's `graph.json` output (node/edge bounds, no absolute
   source paths), inventories all artifacts (no symlinks), and atomically
   publishes a content-addressed overlay snapshot with
   `evidence_class: "semantic_overlay_inference"`.

The overlay is **labeled inference**: a deterministic fingerprint, a producer
(name + version), a backend, and the corpus fingerprint it was built against.
It is disposable — delete it and the canonical graph and kernel are unaffected.

## Explicit processing authority

- `local` — permitted only for the `ollama` backend; refuses non-loopback
  Ollama endpoints.
- `remote` — requires `allow_remote=True`.

## Environment isolation

The subprocess runs with `shell=False`, an explicit command list, a timeout,
and a **restricted environment**: only runtime variables (`PATH`, `HOME`,
`TEMP`, …) plus the selected backend's credential variables are passed through.
No credential is exposed to version probes (which run with runtime env only).

## Security

- Command injection is prevented: `shell=False`, explicit `executable` +
  arguments.
- Overlay output must be a separate directory from the authoritative corpus.
- Output is validated for size, file count, and symlinks; artifacts are
  hash-verified against a manifest.
- Canonical paths are confined; no traversal escapes.
- See `docs/ai/SECURITY_MODEL.md` and `tests/test_security.py`.

## Integration status

The adapter is implemented and covered by the reference/security tests. Full
end-to-end validation requires the external `graphify` binary and a supported
backend, both of which are the operator's responsibility.

## Never

- Never import Graphify into the parsing/kernel path.
- Never label overlay edges as source-backed `code_graph` evidence.
- Never let a missing Graphify installation fail the core build, CLI, or MCP.