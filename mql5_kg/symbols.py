"""Canonical symbol model and deterministic identity rules.

Symbol kinds used by the canonical graph nodes:

``project, file, class, struct, enum, function, method, constructor,
destructor, variable, constant, parameter, property, event_handler, macro,
imported_symbol, external_function, runtime, unknown``

Identity rules
--------------

Symbol IDs are deterministic and derived from semantic identity, never from
unstable line numbers:

- ``file:<sha1(normalized relative path)>``
- ``symbol:<sha1(kind | file | qualified-name | signature)>``
- ``external:<sha1(name)>``        — MQL5 built-ins / unresolved targets
- ``runtime:<sha1(identity)>``     — runtime entities (e.g. MetaTrader terminal)

The same source tree always produces the same IDs; editing a file that changes
a signature produces a new ID for that symbol without perturbing unrelated
symbols (the graph is rebuilt per snapshot anyway).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .graph import SourceLocation, stable_id

# Canonical symbol kinds
KIND_PROJECT = "project"
KIND_FILE = "file"
KIND_CLASS = "class"
KIND_STRUCT = "struct"
KIND_ENUM = "enum"
KIND_FUNCTION = "function"
KIND_METHOD = "method"
KIND_CONSTRUCTOR = "constructor"
KIND_DESTRUCTOR = "destructor"
KIND_VARIABLE = "variable"
KIND_CONSTANT = "constant"
KIND_PARAMETER = "parameter"
KIND_PROPERTY = "property"
KIND_EVENT_HANDLER = "event_handler"
KIND_MACRO = "macro"
KIND_IMPORTED_SYMBOL = "imported_symbol"
KIND_EXTERNAL_FUNCTION = "external_function"
KIND_RUNTIME = "runtime"
KIND_UNKNOWN = "unknown"

SYMBOL_KINDS = frozenset({
    KIND_PROJECT, KIND_FILE, KIND_CLASS, KIND_STRUCT, KIND_ENUM, KIND_FUNCTION,
    KIND_METHOD, KIND_CONSTRUCTOR, KIND_DESTRUCTOR, KIND_VARIABLE, KIND_CONSTANT,
    KIND_PARAMETER, KIND_PROPERTY, KIND_EVENT_HANDLER, KIND_MACRO,
    KIND_IMPORTED_SYMBOL, KIND_EXTERNAL_FUNCTION, KIND_RUNTIME, KIND_UNKNOWN,
})


def file_id(relative_path: str) -> str:
    """Deterministic file node identity."""

    return stable_id("file", relative_path.casefold())


def symbol_id(kind: str, file: str, qualified_name: str, signature: str) -> str:
    """Deterministic symbol node identity from semantic content."""

    return stable_id("symbol", kind, file.casefold(), qualified_name, signature)


def external_id(name: str) -> str:
    """Deterministic external/MQL5 built-in node identity."""

    return stable_id("external", name)


def runtime_id(identity: str) -> str:
    """Deterministic runtime entity identity."""

    return stable_id("runtime", identity)


@dataclass(frozen=True, slots=True)
class Symbol:
    """A resolved symbol record used by adapters and the kernel."""

    id: str
    kind: str
    name: str
    qualified_name: str
    location: SourceLocation | None = None
    attributes: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", dict(self.attributes or {}))
        if self.kind not in SYMBOL_KINDS:
            raise ValueError(f"unknown symbol kind {self.kind!r}")

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "attributes": dict(sorted(self.attributes.items())),
        }
        if self.location is not None:
            value["location"] = self.location.to_dict()
        return value
