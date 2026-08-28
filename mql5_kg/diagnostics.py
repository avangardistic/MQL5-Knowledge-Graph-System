"""Stable diagnostics emitted by tolerant analysis stages.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.

Diagnostic categories (per the canonical design):
- ``parse_error``            LEX/PARSE codes
- ``unresolved_include``     RESOLVE001
- ``unresolved_symbol``      RESOLVE003
- ``ambiguous_symbol``       RESOLVE002
- ``unsupported_construct``  reserved for future analysis stages
- ``graph_warning``          graph validation codes
- ``runtime_warning``        runtime enrichment codes
- ``configuration_error``    analysis configuration codes
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: str
    message: str
    location: "SourceLocation | None" = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.location is not None:
            result["location"] = self.location.to_dict()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Diagnostic":
        from .graph import SourceLocation

        location = value.get("location")
        return cls(
            code=value["code"],
            severity=value["severity"],
            message=value["message"],
            location=SourceLocation.from_dict(location) if location else None,
        )


# Lexer
UNTERMINATED_STRING = "LEX001"
UNTERMINATED_COMMENT = "LEX002"

# Parser
UNMATCHED_DELIMITER = "PARSE001"

# Resolver
UNRESOLVED_INCLUDE = "RESOLVE001"
AMBIGUOUS_CALL = "RESOLVE002"
UNRESOLVED_CALL = "RESOLVE003"

# Source ingestion
DECODE_RECOVERY = "SOURCE001"

# Graph validation
GRAPH_VALIDATION = "GRAPH001"
