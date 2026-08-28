# CLI

The `mql5kg` command is a thin adapter over the Intelligence Kernel. It never
implements graph semantics. Every query command loads a canonical graph,
builds a kernel, and projects the contract result.

## Global options

- `--version`
- Every subcommand supports `--json` for machine-readable output (otherwise
  output is compact human-readable).

## Commands

### `mql5kg index ROOT [-o OUT]`

Index an MQL5 source tree into a canonical graph.

```
mql5kg index ./MQL5/Experts -o graph.json
mql5kg index . --include-root ../Includes --exclude Legacy --max-work 5000000
```

The graph is validated (`GraphSnapshot`) and saved atomically.

### `mql5kg status GRAPH`

Show saved graph metadata: schema version, file/node/edge counts, diagnostic
severities, source fingerprint.

### `mql5kg search GRAPH QUERY [--kind KIND] [--max-items N]`

Fuzzy symbol search across names and qualified names. Preserves exact,
ambiguous, and no-match status.

### `mql5kg symbol GRAPH NAME`

Resolve one symbol: definition, location, signature, attributes.

### `mql5kg callers GRAPH NAME [--max-depth N] [--max-items N]`

Who calls this symbol? (incoming `calls` edges)

### `mql5kg callees GRAPH NAME [--max-depth N] [--max-items N]`

What does this symbol call? (outgoing `calls` edges)

### `mql5kg references GRAPH NAME [--max-depth N]`

All references (incoming + outgoing).

### `mql5kg impact GRAPH NAME [--max-depth N] [--max-items N]`

Upstream impact of changing a symbol, distance-classified.

### `mql5kg trace GRAPH SOURCE TARGET [--max-depth N] [--max-paths N]`

Directed execution paths between two symbols with per-hop evidence, ranked
deterministically.

### `mql5kg context GRAPH NAME [--budget N] [--max-depth N] [--direction D]`

The AI-oriented budgeted context package. This is the token-efficiency
command (see `docs/context-engine.md`).

### `mql5kg diagnostics GRAPH [--max-items N]`

Ordered graph diagnostics.

### `mql5kg export GRAPH --format {graphml,markdown,json} -o OUT`

Export the graph for external tooling.

### `mql5kg serve --graph GRAPH [--host H] [--port P]`

Start the HTTP API adapter (stdlib; blocking).

## Exit codes

- `0` — success
- `1` — invalid parameters, graph load failure, budget exhaustion, or
  intelligence errors (with a machine-readable error envelope under `--json`)

## Legacy compatibility

The historical `graphify` command still works through the compatibility
adapter (`mql5_kg/compat/`):

```bash
python -m mql5_kg.cli.graphify build .            # index + legacy queries
python -m mql5_kg.cli.graphify query symbol OnTick
python -m mql5_kg.cli.graphify query impact ClosePosition
python -m mql5_kg.cli.graphify query trace OnTick OrderSend
python -m mql5_kg.cli.graphify serve              # legacy MCP server
```

These are thin projections over the same kernel (`legacy_find_nodes`,
`legacy_neighborhood`, `legacy_upstream_impact`) — no duplicated semantics.
