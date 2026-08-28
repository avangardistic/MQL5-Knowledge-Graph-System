"""Canonical, backend-neutral graph model and traversal helpers.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.

The ``CodeGraph`` is the single authoritative graph produced by an analysis. It
owns nodes, edges, diagnostics, metadata, schema version, and the source
fingerprint. Serialization is deterministic and file saves are atomic; the
serialized form is a projection, never the semantic engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha1
import json
from pathlib import Path
from typing import Any, Iterable

from .diagnostics import Diagnostic
from .evidence import validate_confidence, validate_origin

SCHEMA_VERSION = "1.0.0"


def stable_id(prefix: str, *parts: object) -> str:
    """Deterministic content-addressed identity."""

    payload = "\x1f".join(str(part) for part in parts)
    digest = sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()[:20]
    return f"{prefix}:{digest}"


@dataclass(frozen=True, slots=True)
class SourceLocation:
    file: str
    line: int
    column: int
    end_line: int | None = None
    end_column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"file": self.file, "line": self.line, "column": self.column}
        if self.end_line is not None:
            value["end_line"] = self.end_line
        if self.end_column is not None:
            value["end_column"] = self.end_column
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SourceLocation":
        return cls(**value)


@dataclass(frozen=True, slots=True)
class GraphNode:
    id: str
    kind: str
    name: str
    qualified_name: str
    location: SourceLocation | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    # Nodes are content-addressed by stable id; hash on the id alone so nodes
    # remain usable in sets even though ``attributes`` is an unhashable dict.
    def __hash__(self) -> int:
        return hash(self.id)

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

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GraphNode":
        location = value.get("location")
        return cls(
            id=value["id"],
            kind=value["kind"],
            name=value["name"],
            qualified_name=value["qualified_name"],
            location=SourceLocation.from_dict(location) if location else None,
            attributes=value.get("attributes", {}),
        )


@dataclass(frozen=True, slots=True)
class GraphEdge:
    id: str
    source: str
    target: str
    relationship: str
    origin: str
    confidence: float
    location: SourceLocation | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_origin(self.origin)
        validate_confidence(self.confidence)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relationship": self.relationship,
            "origin": self.origin,
            "confidence": self.confidence,
            "attributes": dict(sorted(self.attributes.items())),
        }
        if self.location is not None:
            value["location"] = self.location.to_dict()
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GraphEdge":
        location = value.get("location")
        return cls(
            id=value["id"], source=value["source"], target=value["target"],
            relationship=value["relationship"], origin=value["origin"],
            confidence=float(value["confidence"]),
            location=SourceLocation.from_dict(location) if location else None,
            attributes=value.get("attributes", {}),
        )


class CodeGraph:
    def __init__(self, metadata: dict[str, Any] | None = None) -> None:
        self.schema_version = SCHEMA_VERSION
        self.metadata = metadata or {}
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}
        self.diagnostics: list[Diagnostic] = []

    def add_node(self, node: GraphNode) -> GraphNode:
        self.nodes.setdefault(node.id, node)
        return self.nodes[node.id]

    def add_edge(
        self, source: str, target: str, relationship: str, origin: str,
        confidence: float, location: SourceLocation | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> GraphEdge:
        location_key = ""
        if location:
            location_key = f"{location.file}:{location.line}:{location.column}"
        edge_id = stable_id("edge", source, relationship, target, origin, location_key)
        edge = GraphEdge(edge_id, source, target, relationship, origin, confidence,
                         location, attributes or {})
        self.edges.setdefault(edge.id, edge)
        return self.edges[edge.id]

    def add_diagnostic(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "metadata": dict(sorted(self.metadata.items())),
            "nodes": [self.nodes[key].to_dict() for key in sorted(self.nodes)],
            "edges": [self.edges[key].to_dict() for key in sorted(self.edges)],
            "diagnostics": [
                item.to_dict() for item in sorted(
                    self.diagnostics,
                    key=lambda d: (d.severity, d.code, d.location.file if d.location else "",
                                   d.location.line if d.location else 0, d.message),
                )
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(self.to_json(), encoding="utf-8", newline="\n")
        temporary.replace(target)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CodeGraph":
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"Unsupported graph schema: {value.get('schema_version')!r}")
        graph = cls(value.get("metadata", {}))
        for node in value.get("nodes", []):
            graph.add_node(GraphNode.from_dict(node))
        for edge in value.get("edges", []):
            parsed = GraphEdge.from_dict(edge)
            graph.edges[parsed.id] = parsed
        graph.diagnostics = [Diagnostic.from_dict(item) for item in value.get("diagnostics", [])]
        return graph

    @classmethod
    def load(cls, path: str | Path) -> "CodeGraph":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def find_nodes(self, text: str, kind: str | None = None) -> list[GraphNode]:
        from .intelligence import IntelligenceKernel

        return IntelligenceKernel(self).legacy_find_nodes(text, kind)

    def neighborhood(self, seeds: Iterable[str], depth: int = 1) -> dict[str, Any]:
        from .intelligence import IntelligenceKernel

        return IntelligenceKernel(self).legacy_neighborhood(seeds, depth)

    def upstream_impact(self, seeds: Iterable[str], depth: int = 3) -> list[dict[str, Any]]:
        from .intelligence import IntelligenceKernel

        return IntelligenceKernel(self).legacy_upstream_impact(seeds, depth)
