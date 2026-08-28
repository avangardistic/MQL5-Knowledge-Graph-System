# Troubleshooting

## `AnalysisBudgetExceeded: Analysis work budget exhausted`

**Cause:** the deterministic analysis budget (default 1,000,000 units) was
exhausted — typically on large or dense projects.

**Fix:** increase `--max-work` (e.g. `--max-work 5000000`), or narrow scope
with `--exclude`, or narrow `include_roots`. Budget advice is included in the
error `details.recommended_actions`.

> This is by design: analysis fails safely and **never** publishes a partial
> graph. It is not a bug to be removed — raise the budget for bigger repos.

## `graph load failed` / JSON decode error on a graph file

**Cause:** the file is not a valid canonical graph, was truncated, or was
saved by a different schema version.

**Fix:** re-index with `mql5kg index ROOT -o graph.json`. Saves are atomic, so
a partial write should not happen; verify you are pointing at a real graph
file.

## MCP not available (`RuntimeError: MCP server requires the optional 'mcp'`)

**Cause:** the `mcp` extra is not installed.

**Fix:** `pip install -e ".[mcp]"`.

## `reference_dependency_missing` when building a corpus

**Cause:** building a PDF corpus requires `pypdf` + `pypdfium2`.

**Fix:** `pip install -e ".[reference]"`. (Reading/searching an existing
corpus needs no extras.)

## Tests fail only on large-file / timing tests

**Cause:** some timing assertions (e.g. `test_parse_large_file_is_linear`) are
best-effort bounds. On a very slow CI runner they may be tight.

**Fix:** ensure a warm, non-debug Python; the bound is intentionally
generous (30s). Persistent failure may indicate a parser complexity regression
(reintroduced O(functions × bindings)); run the adversarial/regression suite.

## MCP returns `graph_identity_mismatch`

**Cause:** a client passed `expected_source_fingerprint` that differs from the
active snapshot (source changed since index, or wrong root).

**Fix:** re-`index_project` with the current root, then retry. The server
refuses to mix revisions rather than serve stale data (Invariant 6).

## Ambiguity instead of "the answer"

**Cause:** the resolver genuinely cannot disambiguate (same name, multiple
candidates, insufficient type info). This is correct behavior — ambiguity is
preserved (Invariant 4), not guessed away. Pass a qualified name
(`Class::Method`) or `kind` to disambiguate.

## Reference search returns nothing

**Cause:** the corpus was built without an extractable text layer (image-only
PDFs), or the term is absent.

**Fix:** check the corpus `status()`/`warnings` for `empty_or_image_only` /
`extraction_failed`; search a term that exists in the text; verify the corpus
root has a published `current.json`.

## `excluded` accepts names only

**Cause:** `--exclude` validates values as directory names, not paths.
`a/b`, `.`, `..` are rejected on purpose (security).

**Fix:** pass bare directory names, repeatable.

## Windows path issues

The shell here is Git Bash — use POSIX (`ls`, `mv`, `rm`) and forward slashes.
Never `> nul` (creates a literal file), `move`/`del`, or PowerShell cmdlets.

If something isn't listed, open an issue or check `AGENTS.md` and the `docs/ai`
reference set for the authoritative contract and invariant rules.