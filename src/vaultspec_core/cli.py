"""Define the root Typer application and workspace bootstrap flow.

This module is the console entry boundary for the current vault/spec-core CLI.
It registers the mounted command groups, configures logging, resolves the
workspace layout, initializes runtime paths, and then hands control to the
appropriate CLI surface.

Usage:
    Use `app` or `main(...)` as the root CLI boundary, and use `run()` as the
    console-script entrypoint that launches the configured application.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from vaultspec_core.config.workspace import WorkspaceError, resolve_workspace
from vaultspec_core.core.types import init_paths
from vaultspec_core.logging_config import configure_logging
from vaultspec_core.spec_cli import (
    agents_app,
    cmd_doctor,
    cmd_init,
    cmd_readiness,
    cmd_sync_all,
    cmd_test,
    config_app,
    hooks_app,
    rules_app,
    skills_app,
    system_app,
)
from vaultspec_core.vault_cli import app as vault_app

logger = logging.getLogger(__name__)

app = typer.Typer(
    help=(
        "vaultspec-core: Workspace runtime for vaultspec-managed projects.\n\n"
        "Examples:\n"
        "  vaultspec-core init\n"
        "  vaultspec-core sync-all\n"
        '  vaultspec-core vault add --type research --feature example-feature --title "Initial research"\n'
        "  vaultspec-core vault audit --summary\n"
        '  vaultspec-core rules add --name my-rule --content "Do not use mocks."\n'
    ),
    no_args_is_help=True,
)

# Sub-command groups
app.add_typer(vault_app, name="vault")
app.add_typer(rules_app, name="rules")
app.add_typer(skills_app, name="skills")
app.add_typer(agents_app, name="agents")
app.add_typer(config_app, name="config")
app.add_typer(system_app, name="system")
app.add_typer(hooks_app, name="hooks")

# Top-level commands from spec_cli
app.command("sync-all")(cmd_sync_all)
app.command("test")(cmd_test)
app.command("doctor")(cmd_doctor)
app.command("init")(cmd_init)
app.command("readiness")(cmd_readiness)


def version_callback(value: bool):
    if value:
        from vaultspec_core.cli_common import get_version

        typer.echo(get_version())
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    target: Annotated[
        Path | None,
        typer.Option(
            "--target",
            "-t",
            help="Workspace root directory",
            dir_okay=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable INFO logging")
    ] = False,
    debug: Annotated[
        bool, typer.Option("--debug", "-d", help="Enable DEBUG logging")
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show version",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
):
    """Initialize workspace and logging."""
    # 1. Setup logging
    log_level = (
        logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING)
    )
    configure_logging(level=log_level, debug=debug)

    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    # Skip workspace resolution for the init command
    if ctx.invoked_subcommand == "init":
        target_override = target or Path.cwd()
        from vaultspec_core.core import types as _t

        _t.TARGET_DIR = target_override
        ctx.obj = {"target": target_override}
        return

    # 2. Resolve workspace
    try:
        layout = resolve_workspace(target_override=target)
        init_paths(layout)
        ctx.obj = {"target": layout.target_dir, "layout": layout}
    except WorkspaceError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


def run():
    """CLI entry point for console scripts."""
    app()


if __name__ == "__main__":
    app()
