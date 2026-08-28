# Third-Party Notices

Portions of this project are derived from
[`mql5-codegraph`](https://github.com/avangardistic/mql5-codegraph),
which is licensed under the MIT License:

```
MIT License

Copyright (c) 2025 mql5-codegraph contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Derived modules are identified in their docstrings with the line:

> Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.

The derivation was an architectural rewrite: the lexer, tolerant structural
parser, symbol/scope model, resolver, canonical graph, GraphIndex,
Intelligence Kernel, context engine, reference corpus, and adapters were
rebuilt and extended for this project (deterministic budgets, evidence
vocabulary, snapshot immutability, MCP security boundaries, ambiguity
preservation). `mql5-codegraph` is **not** a runtime dependency of this
project; it was used only as a source of ideas and patterns.

Other third-party dependencies:

| Dependency | Purpose | License |
|------------|---------|---------|
| `mcp` (optional extra) | Official MCP SDK for the stdio server | MIT |
| `pypdf`, `pypdfium2` (optional extra) | Reference corpus PDF ingestion | BSD-3-Clause / Apache-2.0 |
| `pytest`, `pytest-asyncio` (dev) | Test runner | MIT |
