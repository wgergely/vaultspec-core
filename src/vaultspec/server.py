"""Unified ``vaultspec-mcp`` server entry point.

Creates a single :class:`FastMCP` instance and registers tool modules.
Each tool module exposes a ``register_tools(mcp)`` function that adds its
``@mcp.tool()`` and ``@mcp.resource()`` endpoints.

Currently registered modules:
- :mod:`vaultspec.subagent_server.server` -- 5 subagent dispatch tools

Future phases will add:
- :mod:`vaultspec.mcp_tools.vault_tools` -- vault audit/management tools
- :mod:`vaultspec.mcp_tools.team_tools` -- multi-agent team tools
- :mod:`vaultspec.mcp_tools.framework_tools` -- framework CLI tools
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP

from vaultspec.subagent_server import (
    initialize_server,
    subagent_lifespan,
)
from vaultspec.subagent_server import (
    register_tools as register_subagent_tools,
)


@asynccontextmanager
async def _lifespan(_app: FastMCP) -> AsyncIterator[None]:
    """Unified server lifespan.

    Composes lifespan contexts from all registered tool modules.
    Currently only the subagent module has a lifespan (agent-file polling).
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
            "and `get_locks` to view active advisory file locks."
        ),
        lifespan=_lifespan,
    )

    # Register tool modules
    register_subagent_tools(mcp)

    return mcp


def main() -> None:
    """Entry point for ``[project.scripts] vaultspec-mcp``.

    Resolves the workspace root, initializes configuration, and starts the
    unified MCP server over stdio transport.
    """
    from vaultspec.core import get_config

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

    mcp = create_server()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    mcp.run()


if __name__ == "__main__":
    main()
