"""MQL5 Knowledge Graph System.

A production-grade MQL5 parser, static-analysis engine, canonical knowledge
graph, code-intelligence engine, and AI integration platform for MQL5
codebases. Builds evidence-backed graphs that let AI coding agents reason
about MQL5 code without consuming the entire source tree.
"""

from .analysis_budget import AnalysisBudget, AnalysisBudgetExceeded
from .graph import CodeGraph, GraphEdge, GraphNode, SCHEMA_VERSION, SourceLocation
from .indexer import analyze_repository, discover_sources
from .parser import parse_source
from .snapshots import GraphSnapshot, GraphValidationError, graph_fingerprint
from .version import __version__

__all__ = [
    "AnalysisBudget",
    "AnalysisBudgetExceeded",
    "CodeGraph",
    "GraphEdge",
    "GraphNode",
    "GraphSnapshot",
    "GraphValidationError",
    "SCHEMA_VERSION",
    "SourceLocation",
    "__version__",
    "analyze_repository",
    "discover_sources",
    "graph_fingerprint",
    "parse_source",
]
