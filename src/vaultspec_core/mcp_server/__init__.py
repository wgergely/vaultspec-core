"""Expose the MCP server package facade for vault/spec-core surfaces.

This package centers on `app` for FastMCP bootstrap and entrypoint behavior,
with `vault_tools` providing the registered MCP tool surface.
"""

from .app import create_server as create_server
from .app import main as main

__all__ = [
    "create_server",
    "main",
]
