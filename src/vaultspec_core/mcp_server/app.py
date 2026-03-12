"""Bootstrap the FastMCP application for the current vault/spec-core tools.

This module constructs the MCP server, attaches the active vault/spec-core tool
surface, and provides the runtime entry boundary for `vaultspec-mcp`. It
supports both root-CLI-injected context and standalone fallback configuration.

Usage:
    Call `create_server()` to construct the configured FastMCP instance, use
    `main(...)` as the Typer callback entry boundary, and use `run()` as the
    zero-argument console-script entrypoint for serving the current tool
    surface.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP

from .vault_tools import register_tools as register_vault_tools

logger = logging.getLogger(__name__)

app = typer.Typer(help="Run the Vaultspec MCP server.")


@asynccontextmanager
async def _lifespan(_app: FastMCP) -> AsyncIterator[None]:
    """Unified server lifespan."""
    yield None


def create_server() -> FastMCP:
    """Create and configure the unified FastMCP server instance."""
    mcp = FastMCP(
        name="vaultspec-mcp",
        instructions=("Unified MCP server for the vaultspec framework. "),
        lifespan=_lifespan,
    )

    # Register tool modules
    register_vault_tools(mcp)

    return mcp


def _serve(ctx_obj: dict | None = None) -> None:
    """Resolve runtime context and start the MCP stdio server."""
    from ..core.types import init_paths
    from ..logging_config import configure_logging

    # Ensure MCP uses stderr for everything to protect JSON-RPC on stdout
    configure_logging()

    # The layout and config may be injected by the root Typer app in cli.py
    if ctx_obj and "layout" in ctx_obj:
        root_dir = ctx_obj["target"]
    else:
        # Fallback if run standalone
        from ..config import get_config

        cfg = get_config()
        root_dir = cfg.target_dir
        if not root_dir:
            typer.echo("Error: Target directory not resolved.", err=True)
            raise typer.Exit(1)

    # Initialize core paths (TARGET_DIR, TEMPLATES_DIR, etc.)
    init_paths(root_dir)

    logger.info("Starting vaultspec-mcp server root=%s", root_dir)

    mcp = create_server()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # FastMCP run() is synchronous, but we can call it here.
    mcp.run()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Typer callback entrypoint for vaultspec-mcp."""
    _serve(ctx.obj)


def run() -> None:
    """Console-script entrypoint for the packaged MCP executable."""
    app()


if __name__ == "__main__":
    run()
