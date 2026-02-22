"""Unified ``vaultspec-mcp`` server entry point.

Creates a single :class:`FastMCP` instance and registers tool modules.
Each tool module exposes a ``register_tools(mcp)`` function that adds its
``@mcp.tool()`` and ``@mcp.resource()`` endpoints.

Registered modules:
- :mod:`vaultspec.mcp_server.subagent_tools` -- 5 subagent dispatch tools
- :mod:`vaultspec.mcp_server.team_tools` -- 8 team coordination tools

Future phases will add:
- :mod:`vaultspec.mcp_server.vault_tools` -- vault audit/management tools
- :mod:`vaultspec.mcp_server.framework_tools` -- framework CLI tools
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP

from .subagent_tools import (
    register_tools as register_subagent_tools,
)
from .subagent_tools import (
    subagent_lifespan,
)
from .team_tools import register_tools as register_team_tools
from .team_tools import set_root_dir as set_team_root_dir


@asynccontextmanager
async def _lifespan(_app: FastMCP) -> AsyncIterator[None]:
    """Unified server lifespan.

    Composes lifespan contexts from all registered tool modules.
    Currently only the subagent module has a lifespan (agent-file polling).

    Args:
        _app: The ``FastMCP`` application instance (unused; required by the
            lifespan protocol).
    """
    async with subagent_lifespan():
        yield None


def create_server() -> FastMCP:
    """Create and configure the unified FastMCP server instance.

    Returns:
        A fully-configured :class:`FastMCP` ready to be run.
    """
    mcp = FastMCP(
        name="vaultspec-mcp",
        instructions=(
            "Unified MCP server for the vaultspec framework. "
            "Use `list_agents` to discover available agents, "
            "`dispatch_agent` to run a sub-agent with a task, "
            "`get_task_status` to check on a running task, "
            "`cancel_task` to cancel a running task, "
            "`get_locks` to view active advisory file locks, "
            "and team tools (`create_team`, `team_status`, `list_teams`, "
            "`dispatch_task`, `broadcast_message`, `send_message`, "
            "`spawn_agent`, `dissolve_team`) for multi-agent coordination."
        ),
        lifespan=_lifespan,
    )

    # Register tool modules
    register_subagent_tools(mcp)
    register_team_tools(mcp)

    return mcp


def main() -> None:
    """Entry point for ``[project.scripts] vaultspec-mcp``.

    Resolves the workspace root, initializes configuration, and starts the
    unified MCP server over stdio transport.
    """
    from ..config import get_config
    from .subagent_tools import initialize_server

    cfg = get_config()

    root_dir = cfg.mcp_root_dir
    if root_dir is None:
        raise RuntimeError(
            "MCP server requires VAULTSPEC_MCP_ROOT_DIR to be set, "
            "or the config to provide a root directory."
        )

    initialize_server(
        root_dir=root_dir,
        ttl_seconds=cfg.mcp_ttl_seconds,
    )
    set_team_root_dir(root_dir)

    mcp = create_server()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    mcp.run()


if __name__ == "__main__":
    main()
