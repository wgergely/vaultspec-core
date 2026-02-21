"""MCP tool registration stubs.

Each sub-module provides a ``register_tools(mcp)`` function that
registers its tools on a FastMCP server instance.
"""

from .framework_tools import register_tools as register_framework_tools
from .team_tools import register_tools as register_team_tools
from .vault_tools import register_tools as register_vault_tools

__all__ = [
    "register_framework_tools",
    "register_team_tools",
    "register_vault_tools",
]
