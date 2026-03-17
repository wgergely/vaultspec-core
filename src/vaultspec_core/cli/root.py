"""Root Typer application with global options and top-level commands.

Mounts vault/spec sub-groups and defines install, uninstall, sync as
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
        "All commands default to the current directory. Use --target / -t\n"
        "to operate on a different directory.\n\n"
        "Examples:\n"
        "  vaultspec-core install\n"
        "  vaultspec-core -t ./my-project install claude\n"
        "  vaultspec-core sync\n"
        "  vaultspec-core spec rules list\n"
    ),
    no_args_is_help=True,
    add_completion=False,
)

# ---- Mount sub-groups -------------------------------------------------------

from .spec_cmd import spec_app  # noqa: E402
from .vault_cmd import vault_app  # noqa: E402

app.add_typer(vault_app, name="vault")
app.add_typer(spec_app, name="spec")


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
            help="Target directory (defaults to current working directory).",
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

    # For install/uninstall the target path is the final destination —
    # workspace resolution may not be possible yet (no .vaultspec/).
    if ctx.invoked_subcommand in ("install", "uninstall"):
        target_path = target or Path.cwd()
        from vaultspec_core.core import types as _t

        _t.TARGET_DIR = target_path
        ctx.obj = {"target": target_path}
        return

    # Resolve workspace for all other commands
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
    ctx: typer.Context,
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
        typer.Option(
            "--force", help="Override contents if installation already exists"
        ),
    ] = False,
) -> None:
    """Deploy the vaultspec framework to the target directory.

    Uses the global --target / -t option (defaults to current directory).
    Scaffolds the workspace structure and syncs all managed resources.
    Use --upgrade to update builtin rules without re-scaffolding.

    Examples:\n
      vaultspec-core install                       # install all providers in cwd\n
      vaultspec-core install core                  # framework only, no providers\n
      vaultspec-core install claude                # framework + claude\n
      vaultspec-core -t ./my-project install       # install in specific directory\n
      vaultspec-core install --upgrade             # update firmware + re-sync\n
      vaultspec-core install claude --dry-run      # preview what would be created\n
    """
    from vaultspec_core.core.commands import install_run

    path: Path = ctx.obj["target"]

    # Guard: refuse to create deeply nested paths — only allow creating the
    # final directory component.  This prevents accidental scaffolding of
    # arbitrary directory trees from typos or path traversal.
    if not path.exists():
        if not path.parent.exists():
            typer.echo(
                f"Error: Parent directory does not exist: {path.parent}\n"
                f"Create intermediate directories manually or use an existing path.",
                err=True,
            )
            raise typer.Exit(code=1)
        if not dry_run:
            path.mkdir(parents=False, exist_ok=True)

    install_run(
        path=path, provider=provider, upgrade=upgrade, dry_run=dry_run, force=force
    )


@app.command("uninstall")
def cmd_uninstall(
    ctx: typer.Context,
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider to uninstall (all, core, claude, gemini, antigravity, codex)"
        ),
    ] = "all",
    remove_vault: Annotated[
        bool,
        typer.Option(
            "--remove-vault",
            help="Also remove .vault/ documentation (preserved by default)",
        ),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview changes without removing")
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Required to execute. Uninstall is destructive."),
    ] = False,
) -> None:
    """Remove the vaultspec framework from the target directory.

    Uses the global --target / -t option (defaults to current directory).
    Removes all managed artifacts (.vaultspec/, provider dirs, generated configs).
    The .vault/ documentation corpus is preserved by default.
    Use a provider name to remove only that provider's artifacts.

    Examples:\n
      vaultspec-core uninstall                    # remove framework, keep .vault/\n
      vaultspec-core uninstall claude             # remove only claude\n
      vaultspec-core -t ./proj uninstall          # remove from specific directory\n
      vaultspec-core uninstall --remove-vault     # also remove .vault/ docs\n
      vaultspec-core uninstall --dry-run          # preview what would be removed\n
    """
    from vaultspec_core.core.commands import uninstall_run

    path: Path = ctx.obj["target"]

    if not path.exists():
        typer.echo(f"Error: Target directory does not exist: {path}", err=True)
        raise typer.Exit(code=1)

    uninstall_run(
        path=path,
        provider=provider,
        keep_vault=not remove_vault,
        dry_run=dry_run,
        force=force,
    )


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

    Defaults to syncing all providers. Pass a provider name to sync only
    that provider (e.g. 'vaultspec-core sync claude').
    """
    if provider == "core":
        typer.echo(
            "Error: 'core' is not a valid sync target. "
            "The sync source is .vaultspec/ (core) itself.",
            err=True,
        )
        raise typer.Exit(code=1)

    from vaultspec_core.core.commands import sync_provider

    sync_provider(provider, prune=prune, dry_run=dry_run, force=force)


# ---- Entry point -------------------------------------------------------------


def run() -> None:
    """CLI entry point for console scripts."""
    app()


if __name__ == "__main__":
    app()
