"""Bootstrap the FastMCP application for the vaultspec MCP server.

Constructs the ``FastMCP`` instance, registers the vault tool surface, and
provides the runtime entry boundary for ``vaultspec-mcp``. Supports both
root-CLI-injected context (via ``ctx.obj``) and standalone fallback
configuration via :func:`~vaultspec_core.config.get_config`.
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
    """Create and configure the FastMCP server instance.

    Instantiates :class:`~mcp.server.fastmcp.FastMCP` and registers the vault
    tool surface via :func:`~vaultspec_core.mcp_server.vault_tools.register_tools`.
    Each tool handler runs in a copied :class:`contextvars.Context` so that
    per-request mutations do not leak between concurrent requests.

    Returns:
        Configured :class:`~mcp.server.fastmcp.FastMCP` instance ready to serve.
    """
    mcp = FastMCP(
        name="vaultspec-mcp",
        instructions=(
            "Vault document discovery and authoring for vaultspec-managed projects."
        ),
        lifespan=_lifespan,
    )

    # Register tool surface (find + create)
    register_vault_tools(mcp)

    return mcp


def _serve(ctx_obj: dict | None = None) -> None:
    """Resolve runtime context, initialise paths, and start the MCP stdio server.

    Configures logging to stderr (to protect JSON-RPC on stdout), resolves
    ``root_dir`` from injected CLI context or fallback config, initialises
    core path globals via ``init_paths``, then calls ``mcp.run()``.

    Args:
        ctx_obj: Optional Typer context object injected by the root CLI app.
            Must contain ``"layout"`` and ``"target"`` keys when present.

    Raises:
        typer.Exit: If ``root_dir`` cannot be resolved in standalone mode.
    """
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
    """Typer callback entrypoint for vaultspec-mcp.

    Args:
        ctx: Typer context carrying the optional ``obj`` dict injected by
            the root CLI app (contains ``"layout"`` and ``"target"`` keys).
    """
    _serve(ctx.obj)


def run() -> None:
    """Console-script entrypoint for the packaged MCP executable."""
    app()


if __name__ == "__main__":
    run()
