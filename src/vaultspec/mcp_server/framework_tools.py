"""Framework configuration MCP tools.

Phase 3 will surface the following CLI functionality as MCP tools:
- list_rules / create_rule / remove_rule / rename_rule / sync_rules
- list_skills / create_skill / remove_skill / rename_skill / sync_skills
- show_config / sync_config
- show_system / sync_system
- sync_all
- doctor / readiness
- list_hooks / trigger_hook
- init

See :mod:`vaultspec.spec_cli` for the corresponding CLI implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["register_tools"]

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP) -> None:
    """Register framework configuration tools on the given FastMCP instance.

    Currently a no-op stub.  Implementation deferred to Phase 3.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """
