# Benchmarking

The project measures — rather than claims — its token-efficiency and
performance. No savings figure is presented without the measurement behind it.

## Token-efficiency benchmark

The benchmark compares three ways to give an AI the context needed for one
representative task (understanding / safely modifying a symbol):

- **Approach A**: the entire repository source.
- **Approach B**: only the files that define the symbol.
- **Approach C**: a bounded context package from the graph (+ targeted source
  around the definition).

### Run it

```bash
# CLI reporter (writes JSON to output if given)
python -m mql5_kg.benchmarks.token_efficiency sample_mql5 --symbol OnTick
python -m mql5_kg.benchmarks.token_efficiency ./MQL5/Experts \
    --symbol OnTick --symbol ClosePosition \
    --max-work 5000000 \
    -o docs/benchmarks/token-efficiency-report.json

# Python API
from mql5_kg.benchmarks.token_efficiency import benchmark_context, run_benchmarks
result = benchmark_context("sample_mql5", "OnTick", context_units=100)
```

### Output

Each measurement records **bytes** and **estimated tokens** (`chars / 4`,
conservative ASCII-oriented estimate) for all three approaches, plus index and
context-cloud latency and graph summary (nodes, edges, diagnostics,
`graph_json_bytes`). Recorded reports live under `docs/benchmarks/`.

### Interpretation

The meaningful win is for representative multi-file codebases: a fixed-budget
context package scales by depth/budget, while raw source scales with the
whole repository. On a representative ~450 KB synthetic repo the context
package is **< 10%** of the raw source tokens (measured in
`tests/test_benchmark_token.py`). For a **tiny** repo the whole source can be
cheaper than a large package — the honest benchmark reports both; it never
claims a universal discount.

### Honesty rules

- Never claim a percentage savings without a recorded measurement.
- Never delete a recorded report because it looks bad — record it.
- The benchmark raises the analysis budget (`--max-work`) when needed so the
  comparison is apples-to-apples on the same repository.

## Performance

- Parsing large files is near-linear due to a precomputed token→function map;
  the O(functions × bindings) bug is regression-tested
  (`test_parser.py::test_parse_large_file_is_linear`).
- Recommended profile points: discovery → lex → parse → resolve → build →
  index → query → context generation → MCP response, plus memory usage for
  small / medium / large repositories.
- Record actual numbers (seconds, bytes, RSS) in `docs/benchmarks/` when you
  profile; do not extrapolate.

## Reproducing

1. Install dev deps and run the test suite (the benchmark test runs the full
   measurement).
2. Run the reporter with a fixed repo + symbol + budget to regenerate JSON.
3. Commit the resulting report so future agents can compare against a
   baseline.