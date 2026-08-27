"""
CLI Module - Command-line interface for MQL5 Knowledge Graph.
"""

__all__ = ['main', 'build_graph', 'query_graph', 'serve_graph']


def __getattr__(name):
    if name in __all__:
        from .graphify import main, build_graph, query_graph, serve_graph
        g = {'main': main, 'build_graph': build_graph,
             'query_graph': query_graph, 'serve_graph': serve_graph}
        return g[name]
    raise AttributeError(f"module 'mql5_kg.cli' has no attribute {name!r}")
