"""Deterministic work accounting for one MQL5 analysis operation.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MAX_WORK = 1_000_000
MAX_MAX_WORK = 10_000_000


@dataclass(frozen=True, slots=True)
class AnalysisBudgetExceeded(RuntimeError):
    """Raised before an analysis action would exceed its work limit."""

    phase: str
    work_used: int
    work_limit: int

    code = "analysis_budget_exceeded"
    message = "Analysis work budget exhausted"

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "details": {
                "phase": self.phase,
                "work_used": self.work_used,
                "work_limit": self.work_limit,
                "budget_kind": "analyzer_work_units",
                "not_model_token_limit": True,
                "recommended_actions": [
                    "narrow_project_root",
                    "narrow_include_roots",
                    "increase_max_work",
                ],
                "maximum_max_work": MAX_MAX_WORK,
            },
        }


class AnalysisBudget:
    """Mutable request-scoped accounting authority for canonical analysis.

    Covers every phase: source discovery, lexing, parsing, resolution, and
    runtime enrichment. When exhausted, an ``AnalysisBudgetExceeded`` error is
    raised and no partial graph is published.
    """

    __slots__ = ("_work_limit", "_work_used")

    def __init__(self, max_work: int | None = None) -> None:
        limit = DEFAULT_MAX_WORK if max_work is None else max_work
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAX_MAX_WORK
        ):
            raise ValueError(
                f"max_work must be an integer between 1 and {MAX_MAX_WORK}"
            )
        self._work_limit = limit
        self._work_used = 0

    @property
    def work_limit(self) -> int:
        return self._work_limit

    @property
    def work_used(self) -> int:
        return self._work_used

    def consume(self, phase: str) -> None:
        """Account for one deterministic unit before starting that unit of work."""

        if self._work_used >= self._work_limit:
            raise AnalysisBudgetExceeded(phase, self._work_used, self._work_limit)
        self._work_used += 1
