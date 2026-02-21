"""Multi-agent team coordination MCP tools.

Phase 4 will surface the following CLI functionality as MCP tools:
- create_team: Create a new multi-agent team
- team_status: Get status of a running team
- list_teams: List active teams
- assign_task: Assign a task to a team member
- broadcast_message: Broadcast a message to all team members
- send_message: Send a message to a specific team member
- dissolve_team: Dissolve a running team

See :mod:`vaultspec.team_cli` for the corresponding CLI implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["register_tools"]

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP) -> None:
    """Register team tools on the given FastMCP instance.

    Currently a no-op stub.  Implementation deferred to Phase 4.
    """
