"""Deprecated ``MQL5Parser`` compatibility facade.

The original regex-based parser is gone; this facade projects the historical
dict-shaped API over the new tolerant parser + resolver, so existing scripts
that consumed ``MQL5Parser`` keep working.

**Deprecated.** New code should use ``mql5_kg.analyze_repository`` /
``mql5_kg.parse_source`` and the canonical ``CodeGraph``. Removed in a future
major version. See ``docs/rewrite/migration-plan.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set

from ..graph import SourceLocation
from ..indexer import analyze_repository
from ..parser import parse_source


class MQL5Parser:
    """Legacy parser facade over the new tolerant pipeline."""

    EVENT_HANDLERS = {
        "OnStart", "OnInit", "OnDeinit", "OnTick", "OnCalculate", "OnTimer",
        "OnTrade", "OnTradeTransaction", "OnBookEvent", "OnChartEvent",
        "OnTester", "OnTesterInit", "OnTesterPass", "OnTesterDeinit",
    }

    def __init__(self) -> None:
        self.symbols: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []
        self.files: Dict[str, Dict[str, Any]] = {}
        self.includes: Dict[str, List[str]] = {}
        self.dll_imports: Dict[str, List[str]] = {}
        self._graph = None

    def parse_file(self, file_path: str) -> Dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as error:
            return {"error": f"Error reading file: {error}"}

        parsed = parse_source(text, path.as_posix())
        self.files[path.as_posix()] = {
            "path": path.as_posix(),
            "name": path.name,
            "size": len(text),
            "lines": text.count("\n") + 1,
        }
        self.includes[path.as_posix()] = [include.target for include in parsed.includes]

        for declaration in parsed.declarations:
            name = declaration.qualified_name
            entry: Dict[str, Any] = {
                "name": declaration.name,
                "type": declaration.kind,
                "file": path.as_posix(),
                "line_start": declaration.location.line,
            }
            if declaration.kind in {"function", "event_handler", "method", "constructor", "destructor", "imported_symbol"}:
                entry["return_type"] = declaration.return_type or "void"
                entry["parameters"] = declaration.signature[
                    declaration.signature.find("(") + 1 : declaration.signature.rfind(")")
                ]
                entry["is_event_handler"] = declaration.kind == "event_handler"
            elif declaration.kind == "input_variable":
                entry["data_type"] = declaration.signature.split()[0] if declaration.signature else "unknown"
            self.symbols[name] = entry
            self.edges.append({
                "source": name,
                "target": path.as_posix(),
                "type": "DEFINED_IN",
            })

        for include in parsed.includes:
            self.edges.append({
                "source": path.as_posix(),
                "target": include.target,
                "type": "INCLUDES",
            })

        for call in parsed.calls:
            if call.caller in self.symbols and call.name in self.symbols:
                self.edges.append({
                    "source": call.caller,
                    "target": call.name,
                    "type": "CALLS",
                })

        return {
            "file": path.as_posix(),
            "symbols_count": len(
                [s for s in self.symbols.values() if s.get("file") == path.as_posix()]
            ),
            "includes": self.includes[path.as_posix()],
            "dll_imports": [],
        }

    def get_graph(self) -> Dict[str, Any]:
        return {
            "symbols": self.symbols,
            "edges": self.edges,
            "files": self.files,
            "includes": self.includes,
            "dll_imports": self.dll_imports,
            "statistics": {
                "total_symbols": len(self.symbols),
                "total_edges": len(self.edges),
                "total_files": len(self.files),
                "by_type": self._count_by_type(),
            },
        }

    def _count_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for symbol in self.symbols.values():
            symbol_type = symbol.get("type", "unknown")
            counts[symbol_type] = counts.get(symbol_type, 0) + 1
        return counts

    def reset(self) -> None:
        self.symbols.clear()
        self.edges.clear()
        self.files.clear()
        self.includes.clear()
        self.dll_imports.clear()
        self._graph = None
