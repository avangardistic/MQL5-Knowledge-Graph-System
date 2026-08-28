"""Legacy module path: ``python -m mql5_kg.cli.graphify``.

Thin re-export of the compatibility adapter over the new core.
"""

from ..compat.graphify import build_graph, main, query_graph, serve_graph

__all__ = ("build_graph", "main", "query_graph", "serve_graph")

if __name__ == "__main__":
    main()
