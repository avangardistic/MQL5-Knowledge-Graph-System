"""Scope model for MQL5 resolution.

The resolver must prefer the correct lexical/semantic scope instead of doing
naive repository-wide name matching. This module defines the scope kinds and
the preference rules applied by ``resolver.py``.

Scope kinds
-----------

- ``global``     — file-level declarations
- ``class``      — members of a class/struct (``owner_name`` in type ranges)
- ``function``   — the function/method body owning a call site
- ``block``      — nested blocks inside a function body (future refinement)
- ``parameter``  — parameters of the enclosing function/method

Preference order for resolving a call site ``foo(...)``:

1. If the call is qualified (``obj.foo`` / ``Class::foo``), use the receiver
   type or explicit qualifier as a hard filter (``receiver_type`` resolution).
2. Otherwise prefer declarations in the same scope as the caller
   (same ``owner`` namespace).
3. Otherwise prefer candidates with matching arity.
4. Otherwise fall back to all candidates by name.
5. If more than one candidate remains, the resolution is **ambiguous** and
   every candidate is preserved — never pick one arbitrarily.

Resolution states (§14): ``resolved | ambiguous | unresolved | inferred``.
"""

from __future__ import annotations

from dataclasses import dataclass

SCOPE_GLOBAL = "global"
SCOPE_CLASS = "class"
SCOPE_FUNCTION = "function"
SCOPE_BLOCK = "block"
SCOPE_PARAMETER = "parameter"

SCOPE_KINDS = frozenset({SCOPE_GLOBAL, SCOPE_CLASS, SCOPE_FUNCTION, SCOPE_BLOCK, SCOPE_PARAMETER})

# Resolution states
STATE_RESOLVED = "resolved"
STATE_AMBIGUOUS = "ambiguous"
STATE_UNRESOLVED = "unresolved"
STATE_INFERRED = "inferred"

RESOLUTION_STATES = frozenset({STATE_RESOLVED, STATE_AMBIGUOUS, STATE_UNRESOLVED, STATE_INFERRED})


@dataclass(frozen=True, slots=True)
class Scope:
    """A lexical scope identity for a declaration or call site."""

    kind: str
    owner: str | None = None      # qualified owner name for class scopes
    function: str | None = None   # qualified function name for function scopes

    def __post_init__(self) -> None:
        if self.kind not in SCOPE_KINDS:
            raise ValueError(f"unknown scope kind {self.kind!r}")

    def to_dict(self) -> dict[str, str | None]:
        return {"kind": self.kind, "owner": self.owner, "function": self.function}
