"""Dependency-free GraphML export.

Portions derived from mql5-codegraph (MIT License). See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from ..graph import CodeGraph


_NS = "http://graphml.graphdrawing.org/xmlns"


def export_graphml(graph: CodeGraph, path: str | Path) -> None:
    ET.register_namespace("", _NS)
    root = ET.Element(f"{{{_NS}}}graphml")
    for key_id, target, name in (
        ("node_kind", "node", "kind"), ("node_name", "node", "name"),
        ("edge_relationship", "edge", "relationship"), ("edge_origin", "edge", "origin"),
        ("edge_confidence", "edge", "confidence"),
    ):
        ET.SubElement(root, f"{{{_NS}}}key", id=key_id, **{"for": target, "attr.name": name,
                                                          "attr.type": "double" if name == "confidence" else "string"})
    graph_element = ET.SubElement(root, f"{{{_NS}}}graph", id="mql5-knowledge-graph", edgedefault="directed")
    for node in sorted(graph.nodes.values(), key=lambda item: item.id):
        element = ET.SubElement(graph_element, f"{{{_NS}}}node", id=node.id)
        ET.SubElement(element, f"{{{_NS}}}data", key="node_kind").text = node.kind
        ET.SubElement(element, f"{{{_NS}}}data", key="node_name").text = node.qualified_name
    for edge in sorted(graph.edges.values(), key=lambda item: item.id):
        element = ET.SubElement(graph_element, f"{{{_NS}}}edge", id=edge.id,
                                source=edge.source, target=edge.target)
        ET.SubElement(element, f"{{{_NS}}}data", key="edge_relationship").text = edge.relationship
        ET.SubElement(element, f"{{{_NS}}}data", key="edge_origin").text = edge.origin
        ET.SubElement(element, f"{{{_NS}}}data", key="edge_confidence").text = str(edge.confidence)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(target, encoding="utf-8", xml_declaration=True)
