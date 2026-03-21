"""FastMCP server exposing vault tools over stdio transport.

Exports :func:`create_server` (factory returning a configured
:class:`fastmcp.FastMCP` instance with ``find`` and ``create`` tools) and
:func:`main` (entry point invoked by the ``vaultspec-mcp`` CLI script).
Depends on :mod:`vaultspec_core.core` for resource operations; consumed
directly by the ``vaultspec-mcp`` console-script entry point.
"""

from .app import create_server as create_server
from .app import main as main

__all__ = [
    "create_server",
    "main",
]
