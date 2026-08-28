"""Stable machine-readable Intelligence Kernel errors.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import json
from typing import Any

from .models import CONTRACT_VERSION


class IntelligenceError(Exception):
    """An expected contract error safe to project through adapters."""

    __slots__ = (
        "contract_version",
        "category",
        "code",
        "message",
        "field",
        "retryable",
    )

    def __init__(
        self,
        category: str,
        code: str,
        message: str,
        *,
        field: str | None = None,
        retryable: bool = False,
        contract_version: str = CONTRACT_VERSION,
    ) -> None:
        super().__init__(message)
        self.contract_version = contract_version
        self.category = category
        self.code = code
        self.message = message
        self.field = field
        self.retryable = retryable

    @classmethod
    def invalid_parameter(cls, field: str, message: str) -> "IntelligenceError":
        return cls(
            "request",
            "invalid_parameter",
            f"{field} {message}",
            field=field,
        )

    @classmethod
    def unsupported_contract_version(cls, value: str) -> "IntelligenceError":
        return cls(
            "compatibility",
            "unsupported_contract_version",
            f"Contract version {value!r} is not supported",
            field="contract_version",
            contract_version=value,
        )

    @classmethod
    def unsupported_operation(cls, operation: str) -> "IntelligenceError":
        return cls(
            "compatibility",
            "unsupported_operation",
            f"Operation {operation!r} is not available",
            field="operation",
        )

    @classmethod
    def unsupported_graph_schema(cls, value: str) -> "IntelligenceError":
        return cls(
            "compatibility",
            "unsupported_graph_schema",
            f"Graph schema {value!r} is not supported",
            field="graph_schema_version",
        )

    @classmethod
    def invalid_request(cls, message: str) -> "IntelligenceError":
        return cls("request", "invalid_request", message)

    @classmethod
    def missing_target(cls, operation: str) -> "IntelligenceError":
        return cls(
            "request",
            "missing_target",
            f"Operation {operation!r} requires a target",
            field="targets",
        )

    @classmethod
    def graph_identity_mismatch(cls) -> "IntelligenceError":
        return cls(
            "state",
            "graph_identity_mismatch",
            "The requested source fingerprint does not match this graph snapshot",
            field="expected_source_fingerprint",
            retryable=True,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "category": self.category,
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "retryable": self.retryable,
        }

    def to_json(self) -> str:
        return json.dumps(
            {"error": self.to_dict()},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
