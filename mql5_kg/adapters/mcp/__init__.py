"""MCP adapter over the Intelligence Kernel.

The MCP server is a thin, read-only projection of kernel operations. It never
implements graph semantics, never expands filesystem access beyond the
operator-selected project root, and keeps all lifecycle logging on stderr so
the stdio protocol stays clean.
"""
