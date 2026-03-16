"""Root Typer application with global options and top-level commands.

Mounts vault/spec/dev sub-groups and defines install, uninstall, sync as
top-level commands that delegate to existing backend functions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

logger = logging.getLogger(__name__)

app = typer.Typer(
    help=(
        "vaultspec-core: Workspace runtime for vaultspec-managed projects.\n\n"
        "Examples:\n"
        "  vaultspec-core install .\n"
        "  vaultspec-core sync\n"
        "  vaultspec-core vault stats\n"
        "  vaultspec-core spec rules list\n"
    ),
    no_args_is_help=True,
    add_completion=False,
)

# ---- Mount sub-groups -------------------------------------------------------

from .dev_cmd import dev_app  # noqa: E402
from .spec_cmd import spec_app  # noqa: E402
from .vault_cmd import vault_app  # noqa: E402

app.add_typer(vault_app, name="vault")
app.add_typer(spec_app, name="spec")
app.add_typer(dev_app, name="dev")


# ---- Global callback --------------------------------------------------------


def _version_callback(value: bool) -> None:
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
            help=(
                "Select installation destination folder."
                ' Use "." for current working directory.'
            ),
            dir_okay=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    debug: Annotated[
        bool, typer.Option("--debug", "-d", help="Enable debug logging")
    ] = False,
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show version",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Initialize workspace and logging."""
    from vaultspec_core.logging_config import configure_logging

    log_level = logging.DEBUG if debug else logging.WARNING
    configure_logging(level=log_level, debug=debug)

    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    # Skip workspace resolution for commands that manage their own target
    if ctx.invoked_subcommand in ("install", "uninstall"):
        target_override = target or Path.cwd()
        from vaultspec_core.core import types as _t

        _t.TARGET_DIR = target_override
        ctx.obj = {"target": target_override}
        return

    # Resolve workspace
    from vaultspec_core.config.workspace import WorkspaceError, resolve_workspace
    from vaultspec_core.core.types import init_paths

    try:
        layout = resolve_workspace(target_override=target)
        init_paths(layout)
        ctx.obj = {"target": layout.target_dir, "layout": layout}
    except WorkspaceError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


# ---- Top-level commands ------------------------------------------------------


@app.command("install")
def cmd_install(
    path: Annotated[
        Path,
        typer.Argument(
            help="Target directory (use '.' for current directory)",
            exists=True,
            dir_okay=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider to install (all, core, claude, gemini, antigravity, codex)"
        ),
    ] = "all",
    upgrade: Annotated[
        bool,
        typer.Option("--upgrade", help="Re-sync builtin rules and firmware"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview changes without writing"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Force install (reserved for Phase 3)"),
    ] = False,
) -> None:
    """Deploy the vaultspec framework to a project directory.

    Scaffolds the workspace structure and syncs all managed resources.
    Use --upgrade to update builtin rules without re-scaffolding.

    Examples:\n
      vaultspec-core install .                    # install all providers\n
      vaultspec-core install . core               # framework only, no providers\n
      vaultspec-core install . claude             # framework + claude\n
      vaultspec-core install . --upgrade          # update firmware + re-sync\n
      vaultspec-core install . claude --dry-run   # preview what would be created\n
    """
    from vaultspec_core.core.commands import install_run

    install_run(path=path, provider=provider, upgrade=upgrade, dry_run=dry_run)


@app.command("uninstall")
def cmd_uninstall(
    path: Annotated[
        Path,
        typer.Argument(
            help="Target directory to remove vaultspec from",
            exists=True,
            dir_okay=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider to uninstall (all, core, claude, gemini, antigravity, codex)"
        ),
    ] = "all",
    keep_vault: Annotated[
        bool,
        typer.Option("--keep-vault", help="Preserve .vault/ documentation"),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview changes without removing")
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Force uninstall (reserved for Phase 3)"),
    ] = False,
) -> None:
    """Remove the vaultspec framework from a project directory.

    Removes all managed artifacts (.vaultspec/, provider dirs, generated configs).
    Use a provider name to remove only that provider's artifacts.

    Examples:\n
      vaultspec-core uninstall .                  # remove everything\n
      vaultspec-core uninstall . claude           # remove only claude\n
      vaultspec-core uninstall . --dry-run        # preview what would be removed\n
    """
    from vaultspec_core.core.commands import uninstall_run

    uninstall_run(path=path, provider=provider, keep_vault=keep_vault, dry_run=dry_run)


@app.command("sync")
def cmd_sync(
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider to sync (all, claude, gemini, antigravity, codex)"
        ),
    ] = "all",
    prune: Annotated[bool, typer.Option("--prune", help="Remove stale files")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite non-managed files")
    ] = False,
) -> None:
    """Sync rules, skills, agents, configs, and system prompts.

    Defaults to syncing all providers.  Pass a provider name to sync only
    that provider (e.g. ``vaultspec-core sync claude``).
    """
    if provider == "core":
        typer.echo(
            "Error: 'core' is not a valid sync target. "
            "The sync source is .vaultspec/ (core) itself.",
            err=True,
        )
        raise typer.Exit(code=1)

    from vaultspec_core.spec_cli import _sync_provider

    _sync_provider(provider, prune=prune, dry_run=dry_run, force=force)


# ---- Entry point -------------------------------------------------------------


def run() -> None:
    """CLI entry point for console scripts."""
    app()


if __name__ == "__main__":
    app()
