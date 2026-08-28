# Parser

The front-end is a tolerant, deterministic MQL5 lexer + structural parser.
It is designed for static analysis of real-world, often imperfect source: it
never crashes on malformed input, preserves source locations, and emits
diagnostics instead of failing the build.

## Lexer

`mql5_kg/lexer.py` tokenizes source into:

- identifiers, keywords, operators, punctuation, literals
- strings (`"..."`, `'...'`) and comments (`//`, `/* */`) that are **immune**
  to analysis — code-like text inside them never becomes a symbol or call edge
- preprocessor directives (`#include`, `#define`, `#property`, `#import`, …)

Every token carries `line`, `column`, and `offset` for evidence.

### Guarantees

```mql5
string x = "OrderSend(foo)";
// ClosePosition();
```

Neither `OrderSend` nor `ClosePosition` produces a `calls` relationship.

## Structural parser

`mql5_kg/parser.py` produces a `ParseResult` containing declarations, call
sites, includes, and diagnostics. It is intentionally not a full C++-style
grammar: it pairs delimiters, locates declaration and body ranges, and
extracts the constructs that matter for a knowledge graph.

### Extracted declarations

| Kind | Example |
|------|---------|
| `function` | `double CalcRisk(double x) { ... }` |
| `method` | `class Engine { void Start(); }` → `Engine::Start` |
| `constructor` / `destructor` | `Engine()`, `~Engine()` |
| `event_handler` | `OnInit`, `OnTick`, `OnTimer`, `OnTrade`, `OnChartEvent`, … |
| `class` / `struct` / `enum` | type ranges with body spans |
| `input_variable` / `sinput` | `input double RiskPercent = 1.5;` |
| `macro` | `#define MAX_POSITIONS 10` |
| `property` | `#property copyright "..."` |
| `imported_symbol` | `#import "kernel32.dll" ... #import` |

For each function-like declaration the parser also records the parameter
count and a best-effort return type.

### Extracted call sites

Each call site records caller, called name, optional receiver qualifier
(`obj.Method()`), receiver type when inferable, argument count, and exact
source location. Control-flow words (`if`, `for`, `while`, `switch`,
`return`, …) are never treated as calls.

### Includes

`#include` lines are captured with their target and whether they are
system-style (`<...>`) or quoted (`"..."`).

## Tolerance

The parser is exercised by the adversarial fixture suite
(`tests/fixtures/adversarial/`) and survives:

- missing semicolons, unclosed blocks (reported as `UNMATCHED_DELIMITER`)
- partially edited / broken source
- missing includes, unresolved identifiers
- duplicate and overloaded symbols
- nested scopes and shadowing
- deep and circular include graphs
- strings/comments that look like code
- large files (linear time: the token→function map is precomputed once)

## Analysis budget

Every parse consumes deterministic logical work units from the shared
`AnalysisBudget`. If the budget is exhausted, `AnalysisBudgetExceeded` is
raised **before** any graph is published; the previous valid snapshot remains
intact. See `docs/ai/SECURITY_MODEL.md` for the reasoning.

## API

```python
from mql5_kg.parser import parse_source

parsed = parse_source(text, "SampleEA.mq5")
for declaration in parsed.declarations:
    print(declaration.kind, declaration.qualified_name, declaration.location.line)
for call in parsed.calls:
    print(call.caller, "->", call.name, call.location.line)
```

For end-to-end analysis use `mql5_kg.indexer.analyze_repository(root)`.
