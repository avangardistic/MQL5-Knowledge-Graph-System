"""Version-negotiating facade over one immutable graph index.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.

The kernel owns the semantic boundary for one published canonical graph
snapshot. All adapters (CLI, HTTP, MCP, compatibility surfaces) project through
it — no adapter implements graph semantics itself.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from typing import Any

from ..context import assemble_context_package
from ..graph import CodeGraph, GraphEdge, SCHEMA_VERSION, stable_id
from ..index import GraphIndex
from .errors import IntelligenceError
from .matching import resolve_target
from .models import (
    Completion,
    DiagnosticResult,
    EvidenceReference,
    GraphIdentity,
    IntelligenceRequest,
    IntelligenceResult,
    NodeSummary,
    TargetResolution,
)
from .paths import TargetDistanceCache, find_directed_paths_between
from .traversal import EvidenceProbe, traverse_context, traverse_impact


class IntelligenceKernel:
    """Own the semantic boundary for one published canonical graph snapshot."""

    __slots__ = (
        "_index",
        "_graph_identity",
        "_evidence_probe",
        "_path_distance_cache",
    )

    def __init__(
        self,
        graph: CodeGraph,
        *,
        snapshot_revision: int | None = None,
        evidence_probe: EvidenceProbe | None = None,
    ) -> None:
        if graph.schema_version != SCHEMA_VERSION:
            raise IntelligenceError.unsupported_graph_schema(graph.schema_version)
        self._index = GraphIndex(graph)
        self._graph_identity = GraphIdentity(
            graph_schema_version=self._index.graph_schema_version,
            source_fingerprint=self._index.source_fingerprint,
            snapshot_revision=snapshot_revision,
        )
        self._evidence_probe = evidence_probe
        self._path_distance_cache = TargetDistanceCache(self._index)

    @property
    def index(self) -> GraphIndex:
        return self._index

    @property
    def graph_identity(self) -> GraphIdentity:
        return self._graph_identity

    def normalize_request(
        self, request: IntelligenceRequest | Mapping[str, Any]
    ) -> IntelligenceRequest:
        if isinstance(request, IntelligenceRequest):
            normalized = request
        elif isinstance(request, Mapping):
            try:
                normalized = IntelligenceRequest.from_dict(request)
            except ValueError as error:
                raw_version = request.get("contract_version")
                if raw_version and str(raw_version).split(".", 1)[0] != "1":
                    raise IntelligenceError.unsupported_contract_version(
                        str(raw_version)
                    ) from error
                message = str(error)
                bound_fields = (
                    "max_depth",
                    "max_items",
                    "max_paths",
                    "max_expansions",
                    "context_units",
                )
                for field in bound_fields:
                    if message.startswith(field):
                        detail = message.removeprefix(field).strip()
                        raise IntelligenceError.invalid_parameter(
                            f"bounds.{field}", detail
                        ) from error
                raise IntelligenceError.invalid_request(str(error)) from error
        else:
            raise IntelligenceError.invalid_request(
                "Intelligence request must be an object"
            )
        expected = normalized.expected_source_fingerprint
        if expected is not None and expected != self._index.source_fingerprint:
            raise IntelligenceError.graph_identity_mismatch()
        return normalized

    def execute(
        self, request: IntelligenceRequest | Mapping[str, Any]
    ) -> Any:
        normalized = self.normalize_request(request)
        handler = getattr(self, f"_execute_{normalized.operation}", None)
        if handler is None:
            raise IntelligenceError.unsupported_operation(normalized.operation)
        return handler(normalized)

    def _require_target(self, request: IntelligenceRequest) -> TargetResolution:
        if len(request.targets) != 1:
            raise IntelligenceError.missing_target(request.operation)
        return resolve_target(self._index, request.targets[0])

    def _execute_query(self, request: IntelligenceRequest) -> IntelligenceResult:
        resolution = self._require_target(request)
        candidates = resolution.candidates
        selected = candidates[: request.bounds.max_items]
        omitted = len(candidates) - len(selected)
        normalized_resolution = TargetResolution(
            selector=resolution.selector,
            status=resolution.status,
            candidates=selected,
            omitted_candidates=omitted,
        )
        if resolution.status == "no_match":
            completion = Completion(True, False, "no_match")
        elif omitted:
            completion = Completion(
                True,
                True,
                "max_items",
                {"nodes": omitted},
                explored_nodes=len(candidates),
            )
        else:
            completion = Completion(
                True, False, "complete", explored_nodes=len(candidates)
            )
        return IntelligenceResult(
            operation=request.operation,
            graph_identity=self._graph_identity,
            request=request,
            resolution=(normalized_resolution,),
            nodes=tuple(
                NodeSummary.from_node(self._index.nodes[item.node_id])
                for item in selected
            ),
            completion=completion,
        )

    def _execute_context(self, request: IntelligenceRequest) -> IntelligenceResult:
        resolution = self._require_target(request)
        if resolution.status == "no_match":
            return IntelligenceResult(
                operation=request.operation,
                graph_identity=self._graph_identity,
                request=request,
                resolution=(resolution,),
                completion=Completion(True, False, "no_match"),
            )
        traversal = traverse_context(
            self._index,
            (candidate.node_id for candidate in resolution.candidates),
            request.bounds,
            direction=request.direction,
            relationship_types=request.relationship_types,
            evidence_probe=self._evidence_probe,
        )
        return IntelligenceResult(
            operation=request.operation,
            graph_identity=self._graph_identity,
            request=request,
            resolution=(resolution,),
            nodes=tuple(NodeSummary.from_node(node) for node in traversal.nodes),
            relationships=traversal.relationships,
            completion=traversal.completion,
        )

    def _execute_impact(self, request: IntelligenceRequest) -> IntelligenceResult:
        resolution = self._require_target(request)
        if resolution.status == "no_match":
            return IntelligenceResult(
                operation=request.operation,
                graph_identity=self._graph_identity,
                request=request,
                resolution=(resolution,),
                completion=Completion(True, False, "no_match"),
            )
        traversal = traverse_impact(
            self._index,
            (candidate.node_id for candidate in resolution.candidates),
            request.bounds,
            relationship_types=request.relationship_types,
            evidence_probe=self._evidence_probe,
        )
        return IntelligenceResult(
            operation=request.operation,
            graph_identity=self._graph_identity,
            request=request,
            resolution=(resolution,),
            nodes=tuple(NodeSummary.from_node(node) for node in traversal.nodes),
            relationships=traversal.relationships,
            completion=traversal.completion,
        )

    def _execute_path(self, request: IntelligenceRequest) -> IntelligenceResult:
        if len(request.targets) != 2:
            raise IntelligenceError.missing_target(request.operation)
        resolutions = tuple(
            resolve_target(self._index, selector) for selector in request.targets
        )
        if any(resolution.status == "no_match" for resolution in resolutions):
            return IntelligenceResult(
                operation=request.operation,
                graph_identity=self._graph_identity,
                request=request,
                resolution=resolutions,
                completion=Completion(True, False, "no_match"),
            )

        search = find_directed_paths_between(
            self._index,
            (candidate.node_id for candidate in resolutions[0].candidates),
            (candidate.node_id for candidate in resolutions[1].candidates),
            request.bounds,
            direction=request.direction,
            relationship_types=request.relationship_types,
            evidence_probe=self._evidence_probe,
            _distance_cache=self._path_distance_cache,
        )
        # Include every node that appears on a returned path so adapters can
        # render stable symbol names without re-implementing resolution.
        path_node_ids = sorted(
            {
                node_id
                for path in search.paths
                for node_id in path.node_ids
            },
            key=lambda node_id: self._index.nodes[node_id].qualified_name.casefold(),
        )
        return IntelligenceResult(
            operation=request.operation,
            graph_identity=self._graph_identity,
            request=request,
            resolution=resolutions,
            nodes=tuple(
                NodeSummary.from_node(self._index.nodes[node_id])
                for node_id in path_node_ids
            ),
            paths=search.paths,
            completion=search.completion,
        )

    def _execute_context_package(
        self, request: IntelligenceRequest
    ) -> IntelligenceResult:
        resolution = self._require_target(request)
        if resolution.status == "no_match":
            return IntelligenceResult(
                operation=request.operation,
                graph_identity=self._graph_identity,
                request=request,
                resolution=(resolution,),
                completion=Completion(True, False, "no_match"),
            )
        packed = assemble_context_package(
            self._index,
            (candidate.node_id for candidate in resolution.candidates),
            request.bounds,
            direction=request.direction,
            relationship_types=request.relationship_types,
            node_kinds=request.node_kinds,
            evidence_probe=self._evidence_probe,
        )
        return IntelligenceResult(
            operation=request.operation,
            graph_identity=self._graph_identity,
            request=request,
            resolution=(resolution,),
            context_package=packed.package,
            completion=packed.completion,
        )

    def _diagnostic_evidence(self, diagnostic_id: str, diagnostic) -> EvidenceReference:
        reason = (
            "location_missing"
            if diagnostic.location is None
            else "probe_not_configured"
        )
        return EvidenceReference(
            subject_id=diagnostic_id,
            origin="extracted",
            confidence=1.0,
            location=diagnostic.location,
            state="unknown",
            state_reason=reason,
        )

    def _execute_diagnostics(
        self, request: IntelligenceRequest
    ) -> IntelligenceResult:
        if request.targets:
            raise IntelligenceError.invalid_request(
                "Operation 'diagnostics' does not accept targets"
            )
        severity_order = {"error": 0, "warning": 1, "info": 2}
        ordered = sorted(
            self._index.diagnostics,
            key=lambda item: (
                severity_order.get(item.severity, 99),
                item.code,
                item.location.file if item.location else "",
                item.location.line if item.location else 0,
                item.location.column if item.location else 0,
                item.message,
            ),
        )
        selected = ordered[: request.bounds.max_items]
        diagnostics = []
        for item in selected:
            location_key = (
                f"{item.location.file}:{item.location.line}:{item.location.column}"
                if item.location
                else ""
            )
            diagnostic_id = stable_id(
                "diagnostic",
                item.severity,
                item.code,
                item.message,
                location_key,
            )
            diagnostics.append(
                DiagnosticResult(
                    id=diagnostic_id,
                    severity=item.severity,
                    code=item.code,
                    message=item.message,
                    evidence=self._diagnostic_evidence(diagnostic_id, item),
                )
            )
        omitted = len(ordered) - len(selected)
        completion = (
            Completion(
                True,
                True,
                "max_items",
                {"diagnostics": omitted},
                explored_nodes=len(ordered),
            )
            if omitted
            else Completion(
                True, False, "complete", explored_nodes=len(ordered)
            )
        )
        return IntelligenceResult(
            operation=request.operation,
            graph_identity=self._graph_identity,
            request=request,
            diagnostics=tuple(diagnostics),
            completion=completion,
        )

    # Compatibility projectors use the same immutable index while preserving
    # every historical bound, shape, and symbol-resolution quirk.
    def legacy_find_nodes(
        self, text: str, kind: str | None = None
    ) -> list:
        needle = text.casefold()
        return sorted(
            (
                node
                for node in self._index.nodes.values()
                if (kind is None or node.kind == kind)
                and (
                    needle in node.name.casefold()
                    or needle in node.qualified_name.casefold()
                )
            ),
            key=lambda node: (node.qualified_name.casefold(), node.id),
        )

    def legacy_neighborhood(
        self, seeds, depth: int = 1
    ) -> dict[str, Any]:
        seen = set(seeds)
        queue = deque((seed, 0) for seed in seen)
        selected_edges = {}
        while queue:
            current, distance = queue.popleft()
            if distance >= depth:
                continue
            incident = (
                tuple(self._index.outgoing.get(current, ()))
                + tuple(self._index.incoming.get(current, ()))
            )
            for edge in incident:
                selected_edges[edge.id] = edge
                other = edge.target if edge.source == current else edge.source
                if other not in seen:
                    seen.add(other)
                    queue.append((other, distance + 1))
        return {
            "nodes": [
                self._index.nodes[node_id].to_dict()
                for node_id in sorted(seen)
                if node_id in self._index.nodes
            ],
            "edges": [
                selected_edges[edge_id].to_dict()
                for edge_id in sorted(selected_edges)
            ],
        }

    def legacy_upstream_impact(
        self, seeds, depth: int = 3
    ) -> list[dict[str, Any]]:
        allowed = {
            "calls",
            "includes",
            "defines",
            "runtime_dispatches",
            "may_trigger_event",
        }
        queue = deque((seed, 0, []) for seed in seeds)
        best = {seed: (0, []) for seed in seeds}
        while queue:
            current, distance, path = queue.popleft()
            if distance >= depth:
                continue
            for edge in self._index.incoming.get(current, ()):
                if edge.relationship not in allowed:
                    continue
                candidate = distance + 1
                new_path = path + [edge.id]
                if (
                    edge.source not in best
                    or candidate < best[edge.source][0]
                ):
                    best[edge.source] = (candidate, new_path)
                    queue.append((edge.source, candidate, new_path))
        return [
            {
                "node": self._index.nodes[node_id].to_dict(),
                "distance": distance,
                "edge_path": path,
            }
            for node_id, (distance, path) in sorted(
                best.items(), key=lambda item: (item[1][0], item[0])
            )
            if distance > 0 and node_id in self._index.nodes
        ]
