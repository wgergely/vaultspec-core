"""FastMCP server exposing vault tools (``find``, ``create``) over stdio."""

from .app import create_server as create_server
from .app import main as main

__all__ = [
    "create_server",
    "main",
]
