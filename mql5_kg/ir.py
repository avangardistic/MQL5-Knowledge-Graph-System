"""Intermediate representation produced by the structural parser.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.

The tolerant parser produces these records directly from the token stream.
They are the IR layer between parsing and resolution: no adapter or resolver
should re-derive structure from raw source.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .diagnostics import Diagnostic
from .graph import SourceLocation


@dataclass(frozen=True, slots=True)
class IncludeRef:
    target: str
    system: bool
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class Declaration:
    kind: str
    name: str
    qualified_name: str
    signature: str
    location: SourceLocation
    body_start: int | None = None
    body_end: int | None = None
    parameter_count: int | None = None
    return_type: str | None = None


@dataclass(frozen=True, slots=True)
class CallSite:
    caller: str
    name: str
    qualifier: str | None
    receiver_type: str | None
    argument_count: int
    location: SourceLocation


@dataclass(slots=True)
class ParseResult:
    file: str
    includes: list[IncludeRef] = field(default_factory=list)
    declarations: list[Declaration] = field(default_factory=list)
    calls: list[CallSite] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
