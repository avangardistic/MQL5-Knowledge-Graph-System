"""Stateful, protocol-neutral service used by the MCP adapter.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Iterable

from ...analysis_budget import AnalysisBudget, AnalysisBudgetExceeded
from ...compiler_evidence import (
    CompilerEvidenceError,
    correlate_compiler_log,
    correlation_result,
)
from ...graph import CodeGraph
from ...indexer import analyze_repository
from ...intelligence import CONTRACT_VERSION, IntelligenceError, IntelligenceKernel
from ...reference import ReferenceCorpus, ReferenceError


class AdapterError(RuntimeError):
    """Expected MCP adapter failure safe to expose without a traceback."""

    __slots__ = ("code", "message", "details")

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": dict(sorted(self.details.items())),
        }

    def to_json(self) -> str:
        return json.dumps(
            {"error": self.to_dict()},
            ensure_ascii=False,
            sort_keys=True,
        )


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    """One successfully published in-memory project graph and kernel."""

    root: Path
    include_roots: tuple[Path, ...]
    excluded: tuple[str, ...]
    revision: int
    graph: CodeGraph
    kernel: IntelligenceKernel


@dataclass(frozen=True, slots=True)
class ReferenceSnapshot:
    """One successfully attached immutable local reference corpus."""

    root: Path
    revision: int
    corpus: ReferenceCorpus


class ProjectSession:
    """Own one active snapshot while keeping failed replacements invisible."""

    __slots__ = ("_index_lock", "_lock", "_snapshot")

    def __init__(self) -> None:
        self._index_lock = Lock()
        self._lock = RLock()
        self._snapshot: ProjectSnapshot | None = None

    @staticmethod
    def _normalize_root(root: str) -> Path:
        if not isinstance(root, str) or not root.strip():
            raise AdapterError(
                "invalid_project_root",
                "Project root must be a non-empty local directory path",
            )
        try:
            resolved = Path(root).expanduser().resolve()
        except (OSError, RuntimeError) as error:
            raise AdapterError(
                "invalid_project_root",
                "Project root could not be resolved",
            ) from error
        if not resolved.is_dir():
            raise AdapterError(
                "invalid_project_root",
                "Project root is not an existing directory",
            )
        return resolved

    @staticmethod
    def _normalize_include_roots(values: Iterable[str]) -> tuple[Path, ...]:
        roots: set[Path] = set()
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise AdapterError(
                    "invalid_tool_arguments",
                    "Every include root must be a non-empty directory path",
                )
            try:
                resolved = Path(value).expanduser().resolve()
            except (OSError, RuntimeError) as error:
                raise AdapterError(
                    "invalid_tool_arguments",
                    "An include root could not be resolved",
                ) from error
            if not resolved.is_dir():
                raise AdapterError(
                    "invalid_tool_arguments",
                    "An include root is not an existing directory",
                )
            roots.add(resolved)
        return tuple(sorted(roots, key=lambda path: str(path).casefold()))

    @staticmethod
    def _normalize_excluded(values: Iterable[str]) -> tuple[str, ...]:
        normalized: set[str] = set()
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise AdapterError(
                    "invalid_tool_arguments",
                    "Every excluded directory name must be a non-empty string",
                )
            item = value.strip()
            if "/" in item or "\\" in item or item in {".", ".."}:
                raise AdapterError(
                    "invalid_tool_arguments",
                    "Excluded values must be directory names, not paths",
                )
            normalized.add(item)
        return tuple(sorted(normalized, key=str.casefold))

    @staticmethod
    def _normalize_max_work(max_work: int | None) -> int | None:
        if max_work is None:
            return None
        try:
            AnalysisBudget(max_work)
        except ValueError as error:
            raise AdapterError(
                "invalid_tool_arguments",
                str(error),
                {"field": "max_work"},
            ) from error
        return max_work

    @staticmethod
    def _status(snapshot: ProjectSnapshot) -> dict[str, Any]:
        return {
            "status": "indexed",
            "revision": snapshot.revision,
            "root": str(snapshot.root),
            "include_roots": [str(path) for path in snapshot.include_roots],
            "excluded": list(snapshot.excluded),
            "graph_identity": snapshot.kernel.graph_identity.to_dict(),
            "counts": {
                "files": int(snapshot.graph.metadata.get("file_count", 0)),
                "nodes": len(snapshot.graph.nodes),
                "edges": len(snapshot.graph.edges),
                "diagnostics": len(snapshot.graph.diagnostics),
            },
        }

    def project_status(self) -> dict[str, Any]:
        with self._lock:
            snapshot = self._snapshot
        if snapshot is None:
            return {"status": "not_indexed", "revision": 0}
        return self._status(snapshot)

    def index_project(
        self,
        root: str,
        include_roots: Iterable[str] = (),
        excluded: Iterable[str] = (),
        *,
        max_work: int | None = None,
    ) -> dict[str, Any]:
        normalized_root = self._normalize_root(root)
        normalized_includes = self._normalize_include_roots(include_roots)
        normalized_excluded = self._normalize_excluded(excluded)
        normalized_max_work = self._normalize_max_work(max_work)

        with self._index_lock:
            try:
                graph = analyze_repository(
                    normalized_root,
                    normalized_includes,
                    normalized_excluded,
                    max_work=normalized_max_work,
                )
            except AnalysisBudgetExceeded as error:
                raise AdapterError(
                    error.code,
                    error.message,
                    error.to_dict()["details"],
                ) from error
            except (OSError, ValueError) as error:
                raise AdapterError(
                    "analysis_failed",
                    "MQL5 project analysis failed",
                    {"reason": str(error)},
                ) from error

            fingerprint = str(graph.metadata.get("source_fingerprint", ""))
            with self._lock:
                current = self._snapshot
                if (
                    current is not None
                    and current.root == normalized_root
                    and current.include_roots == normalized_includes
                    and current.excluded == normalized_excluded
                    and current.kernel.graph_identity.source_fingerprint == fingerprint
                ):
                    result = self._status(current)
                    result["reused"] = True
                    return result

                revision = 1 if current is None else current.revision + 1
                kernel = IntelligenceKernel(graph, snapshot_revision=revision)
                replacement = ProjectSnapshot(
                    root=normalized_root,
                    include_roots=normalized_includes,
                    excluded=normalized_excluded,
                    revision=revision,
                    graph=graph,
                    kernel=kernel,
                )
                self._snapshot = replacement

            result = self._status(replacement)
            result["reused"] = False
            return result

    def _active_snapshot(self) -> ProjectSnapshot:
        with self._lock:
            snapshot = self._snapshot
        if snapshot is None:
            raise AdapterError(
                "project_not_indexed",
                "Index a trusted local MQL5 project before using intelligence tools",
            )
        return snapshot

    @staticmethod
    def _string_tuple(
        values: Iterable[str] | None,
        field_name: str,
    ) -> tuple[str, ...]:
        if values is None:
            return ()
        normalized: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise AdapterError(
                    "invalid_tool_arguments",
                    f"{field_name} must contain only non-empty strings",
                )
            normalized.append(value.strip())
        return tuple(sorted(set(normalized)))

    def _execute(
        self,
        operation: str,
        *,
        targets: list[dict[str, str | None]],
        direction: str,
        relationship_types: Iterable[str] | None = None,
        node_kinds: Iterable[str] | None = None,
        max_depth: int = 1,
        max_items: int = 30,
        max_paths: int = 3,
        max_expansions: int = 10_000,
        context_units: int = 100,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self._active_snapshot()
        request = {
            "contract_version": CONTRACT_VERSION,
            "operation": operation,
            "targets": targets,
            "direction": direction,
            "relationship_types": list(
                self._string_tuple(relationship_types, "relationship_types")
            ),
            "node_kinds": list(self._string_tuple(node_kinds, "node_kinds")),
            "bounds": {
                "max_depth": max_depth,
                "max_items": max_items,
                "max_paths": max_paths,
                "max_expansions": max_expansions,
                "context_units": context_units,
            },
            "expected_source_fingerprint": expected_source_fingerprint,
            "client_request_id": None,
        }
        try:
            return snapshot.kernel.execute(request).to_dict()
        except IntelligenceError as error:
            raise AdapterError(
                "intelligence_error",
                error.message,
                {"intelligence_error": error.to_dict()},
            ) from error
        except ValueError as error:
            normalized = IntelligenceError.invalid_request(str(error))
            raise AdapterError(
                "intelligence_error",
                normalized.message,
                {"intelligence_error": normalized.to_dict()},
            ) from error

    def query_symbols(
        self,
        target: str,
        *,
        kind: str | None = None,
        max_items: int = 30,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            "query",
            targets=[{"value": target, "kind": kind}],
            direction="both",
            max_items=max_items,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    def get_context(
        self,
        target: str,
        *,
        direction: str = "both",
        relationship_types: Iterable[str] | None = None,
        max_depth: int = 1,
        max_items: int = 900,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            "context",
            targets=[{"value": target, "kind": None}],
            direction=direction,
            relationship_types=relationship_types,
            max_depth=max_depth,
            max_items=max_items,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    def get_impact(
        self,
        target: str,
        *,
        relationship_types: Iterable[str] | None = None,
        max_depth: int = 3,
        max_items: int = 2000,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            "impact",
            targets=[{"value": target, "kind": None}],
            direction="incoming",
            relationship_types=relationship_types,
            max_depth=max_depth,
            max_items=max_items,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    def find_paths(
        self,
        source: str,
        target: str,
        *,
        direction: str = "outgoing",
        relationship_types: Iterable[str] | None = None,
        max_depth: int = 5,
        max_paths: int = 3,
        max_expansions: int = 10_000,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            "path",
            targets=[
                {"value": source, "kind": None},
                {"value": target, "kind": None},
            ],
            direction=direction,
            relationship_types=relationship_types,
            max_depth=max_depth,
            max_paths=max_paths,
            max_expansions=max_expansions,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    def get_context_package(
        self,
        target: str,
        *,
        direction: str = "both",
        relationship_types: Iterable[str] | None = None,
        node_kinds: Iterable[str] | None = None,
        max_depth: int = 2,
        max_expansions: int = 10_000,
        context_units: int = 100,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            "context_package",
            targets=[{"value": target, "kind": None}],
            direction=direction,
            relationship_types=relationship_types,
            node_kinds=node_kinds,
            max_depth=max_depth,
            max_expansions=max_expansions,
            context_units=context_units,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    def get_diagnostics(
        self,
        *,
        max_items: int = 250,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            "diagnostics",
            targets=[],
            direction="both",
            max_items=max_items,
            expected_source_fingerprint=expected_source_fingerprint,
        )

    def correlate_compiler_log(
        self,
        log_path: str,
        entry_file: str,
    ) -> dict[str, Any]:
        """Return external compiler evidence for the active immutable snapshot."""

        snapshot = self._active_snapshot()
        try:
            report = correlate_compiler_log(
                snapshot.graph,
                snapshot.root,
                log_path,
                entry_file,
                excluded=snapshot.excluded,
            )
        except CompilerEvidenceError as error:
            raise AdapterError(error.code, error.message) from error
        except (OSError, ValueError) as error:
            raise AdapterError(
                "compiler_correlation_failed",
                "Compiler evidence correlation failed",
            ) from error
        return correlation_result(report, snapshot.kernel.graph_identity)


class ReferenceSession:
    """Own one active reference snapshot independently of the project graph."""

    __slots__ = ("_load_lock", "_lock", "_snapshot")

    def __init__(self) -> None:
        self._load_lock = Lock()
        self._lock = RLock()
        self._snapshot: ReferenceSnapshot | None = None

    @staticmethod
    def _adapt_error(error: ReferenceError) -> AdapterError:
        code = (
            "invalid_tool_arguments"
            if error.code == "invalid_reference_query"
            else error.code
        )
        return AdapterError(code, error.message, error.details)

    @staticmethod
    def _status(snapshot: ReferenceSnapshot) -> dict[str, Any]:
        result = snapshot.corpus.status()
        result["revision"] = snapshot.revision
        result["status"] = "loaded"
        return result

    def reference_status(self) -> dict[str, Any]:
        with self._lock:
            snapshot = self._snapshot
        if snapshot is None:
            return {"status": "not_loaded", "revision": 0}
        return self._status(snapshot)

    def load_reference_corpus(self, corpus_root: str) -> dict[str, Any]:
        if not isinstance(corpus_root, str) or not corpus_root.strip():
            raise AdapterError(
                "invalid_tool_arguments",
                "corpus_root must be a non-empty absolute local directory path",
            )
        try:
            candidate = Path(corpus_root).expanduser()
        except (OSError, RuntimeError) as error:
            raise AdapterError(
                "invalid_tool_arguments",
                "corpus_root could not be resolved",
            ) from error
        if not candidate.is_absolute():
            raise AdapterError(
                "invalid_tool_arguments",
                "corpus_root must be an absolute local directory path",
            )
        with self._load_lock:
            try:
                corpus = ReferenceCorpus.open(candidate)
            except ReferenceError as error:
                raise self._adapt_error(error) from error
            with self._lock:
                current = self._snapshot
                if (
                    current is not None
                    and current.corpus.corpus_fingerprint == corpus.corpus_fingerprint
                ):
                    result = self._status(current)
                    result["reused"] = True
                    return result
                replacement = ReferenceSnapshot(
                    root=corpus.root,
                    revision=1 if current is None else current.revision + 1,
                    corpus=corpus,
                )
                self._snapshot = replacement
            result = self._status(replacement)
            result["reused"] = False
            return result

    def _active_snapshot(
        self,
        expected_corpus_fingerprint: str | None = None,
    ) -> ReferenceSnapshot:
        with self._lock:
            snapshot = self._snapshot
        if snapshot is None:
            raise AdapterError(
                "reference_not_loaded",
                "Attach a complete local reference corpus before using reference tools",
            )
        if expected_corpus_fingerprint is not None:
            if (
                not isinstance(expected_corpus_fingerprint, str)
                or not expected_corpus_fingerprint.strip()
            ):
                raise AdapterError(
                    "invalid_tool_arguments",
                    "expected_corpus_fingerprint must be a non-empty string or null",
                )
            if (
                expected_corpus_fingerprint
                != snapshot.corpus.corpus_fingerprint
            ):
                raise AdapterError(
                    "reference_snapshot_stale",
                    "Active reference corpus does not match the expected fingerprint",
                    {
                        "actual_corpus_fingerprint": snapshot.corpus.corpus_fingerprint,
                        "expected_corpus_fingerprint": expected_corpus_fingerprint,
                    },
                )
        return snapshot

    def search_reference(
        self,
        query: str,
        *,
        limit: int = 20,
        max_excerpt_chars: int = 1_200,
        expected_corpus_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self._active_snapshot(expected_corpus_fingerprint)
        try:
            result = snapshot.corpus.search(
                query,
                limit=limit,
                max_excerpt_chars=max_excerpt_chars,
            )
        except ReferenceError as error:
            raise self._adapt_error(error) from error
        result["snapshot_revision"] = snapshot.revision
        return result

    def get_reference_excerpt(
        self,
        section_id: str,
        *,
        start: int = 0,
        max_chars: int = 1_200,
        expected_corpus_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self._active_snapshot(expected_corpus_fingerprint)
        try:
            result = snapshot.corpus.excerpt(
                section_id,
                start=start,
                max_chars=max_chars,
            )
        except ReferenceError as error:
            raise self._adapt_error(error) from error
        result["snapshot_revision"] = snapshot.revision
        return result
