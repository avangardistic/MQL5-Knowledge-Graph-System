"""Incremental MQL5 analysis with a persisted ParseResult cache.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.

Correctness first (Invariants 5, 12). The incremental model is **sound**:
it re-derives the entire graph through the same deterministic ``build_graph``
resolution pass, so the only cost skipped is re-lexing / re-parsing files
whose bytes are unchanged (they are loaded from a persisted ``FileCache`` of
serialized ``ParseResult`` records keyed by content hash). Repository-wide
resolution always runs over the full declaration/include/call set, which keeps
overload, include, and scope changes correct even though only a few files were
re-parsed.

Guarantees:
- **Determinism**: identical source + compatible cache ⇒ identical graph.
- **No partial publication**: a graph/cache is only written atomically after a
  fully valid graph is built; a failed analysis leaves the previous artifacts
  intact.
- **Safe fallback**: a missing, incompatible, or corrupt cache falls back to a
  full rebuild (never an unsafe partial resolution).
- **Reuse**: unchanged repository reuses the cached ParseResults wholesale.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from .analysis_budget import AnalysisBudget
from .diagnostics import Diagnostic, DECODE_RECOVERY
from .graph import CodeGraph, SourceLocation
from .ir import CallSite, Declaration, IncludeRef, ParseResult
from .indexer import DEFAULT_EXCLUDED_DIRECTORIES, discover_sources
from .parser import parse_source
from .resolver import ParsedUnit, build_graph
from .runtime import enrich_runtime

CACHE_SCHEMA_VERSION = "1.0.0"


def file_content_hash(data: bytes) -> str:
    """Deterministic SHA-256 over raw file bytes."""

    return sha256(data, usedforsecurity=False).hexdigest()


# ---------------------------------------------------------------------------
# ParseResult serialization (versioned, deterministic)
# ---------------------------------------------------------------------------

def _location_to_dict(location: SourceLocation | None) -> dict[str, Any] | None:
    return location.to_dict() if location is not None else None


def _location_from_dict(value: Any) -> SourceLocation | None:
    return SourceLocation.from_dict(value) if value else None


def deserialize_parse_result(value: Mapping[str, Any], file: str) -> ParseResult:
    """Reconstruct a ParseResult from a serialized record.

    Raises ``ValueError`` on any incompatible record so a corrupt/incompatible
    cache entry triggers a safe fresh parse instead of a bad graph.
    """

    if value.get("schema") != CACHE_SCHEMA_VERSION:
        raise ValueError(f"Unsupported ParseResult cache schema: {value.get('schema')!r}")
    result_file = str(value.get("file", file))
    includes = []
    for item in value.get("includes", ()):
        if not isinstance(item, dict):
            raise ValueError("invalid include record")
        includes.append(IncludeRef(
            target=str(item["target"]),
            system=bool(item.get("system", False)),
            location=_location_from_dict(item.get("location")),
        ))
    declarations = []
    for item in value.get("declarations", ()):
        if not isinstance(item, dict):
            raise ValueError("invalid declaration record")
        declarations.append(Declaration(
            kind=str(item["kind"]),
            name=str(item["name"]),
            qualified_name=str(item["qualified_name"]),
            signature=str(item["signature"]),
            location=_location_from_dict(item.get("location")),
            body_start=item.get("body_start"),
            body_end=item.get("body_end"),
            parameter_count=item.get("parameter_count"),
            return_type=item.get("return_type"),
        ))
    calls = []
    for item in value.get("calls", ()):
        if not isinstance(item, dict):
            raise ValueError("invalid call-site record")
        calls.append(CallSite(
            caller=str(item["caller"]),
            name=str(item["name"]),
            qualifier=item.get("qualifier"),
            receiver_type=item.get("receiver_type"),
            argument_count=int(item.get("argument_count", 0)),
            location=_location_from_dict(item.get("location")),
        ))
    diagnostics = []
    for item in value.get("diagnostics", ()):
        if not isinstance(item, dict):
            raise ValueError("invalid diagnostic record")
        diagnostics.append(Diagnostic(
            code=str(item["code"]),
            severity=str(item["severity"]),
            message=str(item["message"]),
            location=_location_from_dict(item.get("location")),
        ))
    return ParseResult(
        file=result_file,
        includes=includes,
        declarations=declarations,
        calls=calls,
        diagnostics=diagnostics,
    )


def _serialize_parse_result(file: str, result: ParseResult) -> dict[str, Any]:
    return {
        "schema": CACHE_SCHEMA_VERSION,
        "file": file,
        "includes": [
            {"target": item.target, "system": item.system,
             "location": _location_to_dict(item.location)}
            for item in result.includes
        ],
        "declarations": [
            {
                "kind": item.kind,
                "name": item.name,
                "qualified_name": item.qualified_name,
                "signature": item.signature,
                "location": _location_to_dict(item.location),
                "body_start": item.body_start,
                "body_end": item.body_end,
                "parameter_count": item.parameter_count,
                "return_type": item.return_type,
            }
            for item in result.declarations
        ],
        "calls": [
            {
                "caller": item.caller,
                "name": item.name,
                "qualifier": item.qualifier,
                "receiver_type": item.receiver_type,
                "argument_count": item.argument_count,
                "location": _location_to_dict(item.location),
            }
            for item in result.calls
        ],
        "diagnostics": [
            {
                "code": item.code,
                "severity": item.severity,
                "message": item.message,
                "location": _location_to_dict(item.location),
            }
            for item in result.diagnostics
        ],
    }


# ---------------------------------------------------------------------------
# Config identity
# ---------------------------------------------------------------------------

def config_fingerprint(
    root: Path,
    include_roots: Iterable[Path],
    excluded: Iterable[str],
) -> str:
    """Deterministic identity for an analysis configuration.

    The cache is only reused when the configuration matches exactly, so
    changing include roots, excluded names, or the root safely invalidates the
    cache (the next call does a full rebuild and re-populates the cache).
    """

    payload = json.dumps(
        {
            "root": root.as_posix(),
            "include_roots": sorted(path.as_posix() for path in include_roots),
            "excluded": sorted(set(DEFAULT_EXCLUDED_DIRECTORIES) | set(excluded)),
            "schema": CACHE_SCHEMA_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8"), usedforsecurity=False).hexdigest()


# ---------------------------------------------------------------------------
# FileCache
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FileCache:
    """Persisted per-file parse cache: content hash → serialized ParseResult.

    Each record stores the relative path that first produced that hash, so
    deleted files are reportable. The whole cache is one JSON object for
    atomic load/save (temp + replace); cardinality is bounded by the
    repository's file count.
    """

    records: dict[str, dict[str, Any]]
    fingerprint: str | None = None

    @classmethod
    def empty(cls) -> "FileCache":
        return cls(records={}, fingerprint=None)

    @classmethod
    def load(cls, path: Path) -> "FileCache":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return cls.empty()
        if not isinstance(payload, dict) or payload.get("schema") != CACHE_SCHEMA_VERSION:
            return cls.empty()
        records = payload.get("records", {})
        if not isinstance(records, dict):
            return cls.empty()
        return cls(records=records, fingerprint=payload.get("config_fingerprint"))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(path)

    def _to_dict(self) -> dict[str, Any]:
        return {
            "schema": CACHE_SCHEMA_VERSION,
            "config_fingerprint": self.fingerprint,
            "records": {hash_: record for hash_, record in sorted(self.records.items())},
        }

    def record_path(self, content_hash: str) -> str | None:
        record = self.records.get(content_hash)
        path = record.get("file") if isinstance(record, dict) else None
        return path if isinstance(path, str) else None


# ---------------------------------------------------------------------------
# Analysis result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class IncrementalResult:
    """Outcome of one analysis: graph plus an honest change/mode report."""

    graph: CodeGraph
    mode: str  # "reuse" | "incremental" | "full"
    reused_files: int = 0
    changed_files: tuple[str, ...] = ()
    removed_files: tuple[str, ...] = ()
    analysis_time_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "reused_files": self.reused_files,
            "changed_files": list(self.changed_files),
            "removed_files": list(self.removed_files),
            "analysis_time_seconds": round(self.analysis_time_seconds, 4),
            "files": self.graph.metadata.get("file_count", 0),
            "nodes": len(self.graph.nodes),
            "edges": len(self.graph.edges),
            "diagnostics": len(self.graph.diagnostics),
            "source_fingerprint": self.graph.metadata.get("source_fingerprint"),
        }


def incremental_analysis(
    root: str | Path,
    include_roots: Iterable[str | Path] = (),
    excluded: Iterable[str] = (),
    *,
    max_work: int | None = None,
    budget: AnalysisBudget | None = None,
    cache_path: str | Path | None = None,
    cache: FileCache | None = None,
) -> tuple[IncrementalResult, FileCache]:
    """Analyze a repository, reusing parsed unchanged files from a cache.

    ``cache_path`` enables disk persistence (load + save). ``cache`` enables
    in-memory reuse. With neither, this behaves like a full build and returns
    an empty cache. Returns ``(IncrementalResult, FileCache)``. Raise
    ``ValueError`` if both ``budget`` and ``max_work`` are given.
    """

    if budget is not None and max_work is not None:
        raise ValueError("Specify either max_work or budget, not both")
    active_budget = budget or AnalysisBudget(max_work)
    started = time.monotonic()

    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"Analysis root is not a directory: {root_path}")
    include_paths: list[Path] = []
    for path in include_roots:
        active_budget.consume("source_discovery")
        include_paths.append(Path(path).resolve())

    resolved_cache_path = Path(cache_path).resolve() if cache_path is not None else None
    loaded_cache = cache
    if loaded_cache is None and resolved_cache_path is not None:
        loaded_cache = FileCache.load(resolved_cache_path)
    if loaded_cache is None:
        loaded_cache = FileCache.empty()

    cfg = config_fingerprint(root_path, include_paths, excluded)
    config_match = loaded_cache.fingerprint == cfg and len(loaded_cache.records) > 0

    source_paths = discover_sources(root_path, excluded, budget=active_budget)
    fresh: list[tuple[Path, str, str, bytes]] = []
    hash_to_relative: dict[str, str] = {}
    for path in source_paths:
        active_budget.consume("source_discovery")
        relative = path.relative_to(root_path).as_posix()
        data = path.read_bytes()
        digest = file_content_hash(data)
        hash_to_relative[digest] = relative
        fresh.append((path, relative, digest, data))

    current_hashes = set(hash_to_relative.keys())
    cached_hashes = set(loaded_cache.records.keys())
    reused_hashes = cached_hashes & current_hashes if config_match else set()
    added_hashes = current_hashes - reused_hashes
    removed_hashes = cached_hashes - current_hashes if config_match else set()

    changed_files = tuple(
        hash_to_relative[d] for d in sorted(added_hashes, key=lambda h: hash_to_relative[h].casefold())
    )
    removed_files = tuple(
        sorted(
            (loaded_cache.record_path(d) for d in removed_hashes),
            key=str.casefold,
        )
    )

    # Build the new cache; reuse records for unchanged hashes, replace for
    # changed, drop for removed.
    next_records: dict[str, dict[str, Any]] = {}
    decoded: list[Diagnostic] = []
    units: list[ParsedUnit] = []
    reused_files = 0

    for path, relative, digest, data in fresh:
        active_budget.consume("source_discovery")
        if digest in reused_hashes:
            record = loaded_cache.records[digest]
            try:
                parsed = deserialize_parse_result(record, relative)
            except (ValueError, KeyError, TypeError):
                parsed = _fresh_parse(relative, data, active_budget, decoded)
                record = _serialize_parse_result(relative, parsed)
            else:
                reused_files += 1
            next_records[digest] = record
        else:
            parsed = _fresh_parse(relative, data, active_budget, decoded)
            next_records[digest] = _serialize_parse_result(relative, parsed)
        units.append(ParsedUnit(path.resolve(), relative, parsed))

    next_cache = FileCache(records=next_records, fingerprint=cfg)

    # Source fingerprint must match analyze_repository: sorted relative paths +
    # raw bytes, deterministically.
    digest = sha256()
    for _, relative, _, data in sorted(fresh, key=lambda item: item[1].casefold()):
        active_budget.consume("source_discovery")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    source_fingerprint = digest.hexdigest()

    graph, _ = build_graph(
        units,
        root_path,
        include_paths,
        source_fingerprint,
        budget=active_budget,
    )
    for diagnostic in decoded:
        graph.add_diagnostic(diagnostic)
    enrich_runtime(graph, budget=active_budget)

    if reused_hashes == current_hashes and config_match and not removed_hashes:
        mode = "reuse"
    elif config_match:
        mode = "incremental"
    else:
        mode = "full"

    graph.metadata["incremental_mode"] = mode
    graph.metadata.update({
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "diagnostic_count": len(graph.diagnostics),
    })

    result = IncrementalResult(
        graph=graph,
        mode=mode,
        reused_files=reused_files,
        changed_files=changed_files,
        removed_files=removed_files,
        analysis_time_seconds=time.monotonic() - started,
    )
    return result, next_cache


def _fresh_parse(
    relative: str,
    data: bytes,
    budget: AnalysisBudget,
    decoded: list[Diagnostic],
) -> ParseResult:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
        decoded.append(Diagnostic(
            DECODE_RECOVERY, "warning",
            "Invalid UTF-8 bytes replaced during decoding",
            SourceLocation(relative, 1, 1),
        ))
    return parse_source(text, relative, budget=budget)


def persist_incremental(
    result: IncrementalResult,
    cache: FileCache,
    *,
    graph_path: Path | None = None,
    cache_path: Path | None = None,
) -> None:
    """Atomically persist a validated analysis graph + cache together.

    The cache is written after the graph; each save is atomic, so a crash
    mid-persist leaves a valid previous graph or cache, never a torn file.
    """

    if graph_path is not None:
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        result.graph.save(graph_path)
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache.save(cache_path)