"""Read-only correlation of bounded MetaEditor compiler evidence with a static graph.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.

Compiler evidence is external evidence: it never mutates the canonical graph,
and a successful compile is never interpreted as proof that runtime or trading
behavior is correct.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any, Iterable

from .graph import CodeGraph, SourceLocation
from .indexer import observe_source_identity
from .intelligence.models import GraphIdentity


CONTRACT_VERSION = "1.0.0"
MAX_LOG_BYTES = 2 * 1024 * 1024
MAX_DIAGNOSTICS = 1_000

_SUMMARY = re.compile(
    r"\bResult:\s*(?P<errors>\d+)\s+errors?,\s*"
    r"(?P<warnings>\d+)\s+warnings?\b",
    re.IGNORECASE,
)
_DIAGNOSTIC = re.compile(
    r"^\s*(?P<path>[^()\r\n]+?)\s*"
    r"\(\s*(?P<line>\d+)\s*,\s*(?P<column>\d+)\s*\)\s*:\s*"
    r"(?P<severity>error|warning)\s*(?P<code>\d+)?\s*:\s*"
    r"(?P<message>.+?)\s*$",
    re.IGNORECASE,
)
_UNLOCATED_DIAGNOSTIC = re.compile(
    r"^\s*(?P<severity>error|warning)\s*(?P<code>\d+)?\s*:\s*"
    r"(?P<message>.+?)\s*$",
    re.IGNORECASE,
)


class CompilerEvidenceError(RuntimeError):
    """A safe compiler-evidence boundary failure for local adapters."""

    __slots__ = ("code", "message")

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class CompilerDiagnostic:
    severity: str
    code: str | None
    message: str
    location: SourceLocation | None
    correlation: dict[str, str | None]

    def to_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "location": self.location.to_dict() if self.location else None,
            "correlation": dict(sorted(self.correlation.items())),
        }


@dataclass(frozen=True, slots=True)
class CompilerEvidenceReport:
    source_fingerprint: str
    current_source_fingerprint: str
    graph_is_current: bool
    log_fingerprint: str
    observed_at: str
    evidence_state: str
    outcome: str
    complete: bool
    entry_file: str
    diagnostics: tuple[CompilerDiagnostic, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_fingerprint": self.source_fingerprint,
            "current_source_fingerprint": self.current_source_fingerprint,
            "graph_is_current": self.graph_is_current,
            "log_fingerprint": self.log_fingerprint,
            "observed_at": self.observed_at,
            "evidence_state": self.evidence_state,
            "outcome": self.outcome,
            "complete": self.complete,
            "entry_file": self.entry_file,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


def _resolve_contained(root: Path, value: str | Path, *, entry: bool = False) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise CompilerEvidenceError(
            "compiler_log_invalid",
            "Compiler log and entry file must be non-empty local paths",
        )
    supplied = Path(value)
    candidate = supplied if supplied.is_absolute() else root / supplied
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as error:
        raise CompilerEvidenceError(
            "compiler_log_outside_root",
            "Compiler log and entry file must remain under the selected project root",
        ) from error
    if not resolved.is_file():
        raise CompilerEvidenceError(
            "compiler_log_invalid",
            "Compiler log or entry file is not an existing regular file",
        )
    if entry and resolved.suffix.lower() != ".mq5":
        raise CompilerEvidenceError(
            "compiler_log_invalid",
            "Compiler entry file must be an existing .mq5 source file",
        )
    return resolved


def _read_log(path: Path) -> tuple[bytes, str, bool]:
    try:
        size = path.stat().st_size
    except OSError as error:
        raise CompilerEvidenceError(
            "compiler_log_unreadable",
            "Compiler log could not be read",
        ) from error
    if size > MAX_LOG_BYTES:
        raise CompilerEvidenceError(
            "compiler_log_too_large",
            f"Compiler log exceeds the {MAX_LOG_BYTES} byte limit",
        )
    try:
        data = path.read_bytes()
    except OSError as error:
        raise CompilerEvidenceError(
            "compiler_log_unreadable",
            "Compiler log could not be read",
        ) from error
    if not data:
        raise CompilerEvidenceError("compiler_log_invalid", "Compiler log is empty")
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    try:
        return data, data.decode(encoding), False
    except UnicodeDecodeError:
        return data, data.decode(encoding, errors="replace"), True


def _diagnostic_location(root: Path, raw_path: str, line: int, column: int) -> SourceLocation | None:
    value = raw_path.strip().strip('"').strip("'")
    candidate = Path(value)
    if (
        not candidate.is_absolute()
        and (
            PureWindowsPath(value).is_absolute()
            or PurePosixPath(value).is_absolute()
        )
    ):
        return None
    candidate = candidate if candidate.is_absolute() else root / candidate
    try:
        relative = candidate.resolve().relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError):
        return None
    return SourceLocation(relative, line, column)


def _correlation(
    graph: CodeGraph,
    location: SourceLocation | None,
    *,
    had_location: bool,
) -> dict[str, str | None]:
    if location is None:
        return {
            "state": "outside_project" if had_location else "unlocated",
            "origin": None,
        }
    matches = sorted(
        (
            node
            for node in graph.nodes.values()
            if node.location is not None
            and node.location.file.casefold() == location.file.casefold()
            and node.location.line == location.line
        ),
        key=lambda node: node.id,
    )
    if not matches:
        return {"state": "no_declaration", "origin": "compiler_location"}
    if len(matches) > 1:
        return {"state": "ambiguous", "origin": "compiler_location"}
    node = matches[0]
    return {
        "state": "exact",
        "origin": "compiler_location",
        "symbol_id": node.id,
        "qualified_name": node.qualified_name,
    }


def _parse_diagnostics(root: Path, text: str, graph: CodeGraph) -> tuple[CompilerDiagnostic, ...]:
    diagnostics: list[CompilerDiagnostic] = []
    for raw_line in text.splitlines():
        match = _DIAGNOSTIC.match(raw_line)
        had_location = match is not None
        if match is None:
            match = _UNLOCATED_DIAGNOSTIC.match(raw_line)
        if match is None:
            continue
        if len(diagnostics) >= MAX_DIAGNOSTICS:
            raise CompilerEvidenceError(
                "compiler_log_invalid",
                f"Compiler log exceeds the {MAX_DIAGNOSTICS} diagnostic limit",
            )
        location = (
            _diagnostic_location(
                root,
                match.group("path"),
                int(match.group("line")),
                int(match.group("column")),
            )
            if had_location
            else None
        )
        diagnostics.append(
            CompilerDiagnostic(
                severity=match.group("severity").casefold(),
                code=match.group("code"),
                message=match.group("message").strip(),
                location=location,
                correlation=_correlation(graph, location, had_location=had_location),
            )
        )
    return tuple(
        sorted(
            diagnostics,
            key=lambda item: (
                item.location.file.casefold() if item.location else "\uffff",
                item.location.line if item.location else 0,
                item.location.column if item.location else 0,
                item.severity,
                item.code or "",
                item.message,
            ),
        )
    )


def _summary(text: str) -> tuple[int, int] | None:
    matches = tuple(_SUMMARY.finditer(text))
    if len(matches) != 1:
        return None
    return int(matches[0].group("errors")), int(matches[0].group("warnings"))


def correlate_compiler_log(
    graph: CodeGraph,
    root: str | Path,
    log_path: str | Path,
    entry_file: str | Path,
    *,
    excluded: Iterable[str] = (),
) -> CompilerEvidenceReport:
    """Return bounded external compiler evidence without mutating the graph or project."""

    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise CompilerEvidenceError(
            "compiler_correlation_failed",
            "Selected project root is not an existing directory",
        )
    source_fingerprint = graph.metadata.get("source_fingerprint")
    if not isinstance(source_fingerprint, str) or not source_fingerprint:
        raise CompilerEvidenceError(
            "compiler_correlation_failed",
            "Graph is missing a source fingerprint required for compiler correlation",
        )
    entry_path = _resolve_contained(root_path, entry_file, entry=True)
    resolved_log = _resolve_contained(root_path, log_path)
    try:
        source_before = observe_source_identity(root_path, excluded)
    except (OSError, ValueError, RuntimeError) as error:
        raise CompilerEvidenceError(
            "compiler_correlation_failed",
            "Current source identity could not be observed",
        ) from error
    data, text, recovered_text = _read_log(resolved_log)
    diagnostics = _parse_diagnostics(root_path, text, graph)
    summary = _summary(text)
    try:
        log_stat = resolved_log.stat()
        observed_at = datetime.fromtimestamp(
            log_stat.st_mtime, timezone.utc
        ).isoformat().replace("+00:00", "Z")
    except OSError as error:
        raise CompilerEvidenceError(
            "compiler_log_unreadable",
            "Compiler log could not be read",
        ) from error
    try:
        identity = observe_source_identity(root_path, excluded)
    except (OSError, ValueError, RuntimeError) as error:
        raise CompilerEvidenceError(
            "compiler_correlation_failed",
            "Current source identity could not be observed",
        ) from error
    graph_is_current = identity.fingerprint == source_fingerprint
    if summary is None:
        complete = False
        outcome = "unknown"
    else:
        errors, warnings = summary
        parsed_errors = sum(item.severity == "error" for item in diagnostics)
        parsed_warnings = sum(item.severity == "warning" for item in diagnostics)
        complete = not recovered_text and errors == parsed_errors and warnings == parsed_warnings
        outcome = (
            "errors" if errors else "warnings" if warnings else "success"
        ) if complete else "unknown"
    if not complete:
        evidence_state = "incomplete"
    elif (
        source_before != identity
        or not graph_is_current
        or log_stat.st_mtime_ns < identity.latest_mtime_ns
    ):
        evidence_state = "stale"
    else:
        evidence_state = "current"
    return CompilerEvidenceReport(
        source_fingerprint=source_fingerprint,
        current_source_fingerprint=identity.fingerprint,
        graph_is_current=graph_is_current,
        log_fingerprint=sha256(data).hexdigest(),
        observed_at=observed_at,
        evidence_state=evidence_state,
        outcome=outcome,
        complete=complete,
        entry_file=entry_path.relative_to(root_path).as_posix(),
        diagnostics=diagnostics,
    )


def correlation_result(
    report: CompilerEvidenceReport,
    graph_identity: GraphIdentity,
) -> dict[str, Any]:
    """Wrap one report in the stable adapter-facing compiler-evidence envelope."""

    return {
        "contract_version": CONTRACT_VERSION,
        "graph_identity": graph_identity.to_dict(),
        "compiler_evidence": report.to_dict(),
    }
