"""Root Typer application: global callback, options, and top-level commands.

Mounts :mod:`.vault_cmd` and :mod:`.spec_cmd` sub-groups and defines
``install``, ``uninstall``, and ``sync`` commands that delegate to
:mod:`vaultspec_core.core.commands`. Exposes :func:`run` as the console-script
entry point. Depends on :mod:`vaultspec_core.config.workspace` for workspace
resolution and :mod:`vaultspec_core.core.types` for global path initialization.
"""

import logging
from pathlib import Path
from typing import Annotated

import typer

from vaultspec_core.cli._target import (
    TargetOption,
    apply_target,
    apply_target_install,
)

logger = logging.getLogger(__name__)

app = typer.Typer(
    help=(
        "vaultspec-core: Workspace runtime for vaultspec-managed projects.\n\n"
        "All commands default to the current directory. Use --target / -t\n"
        "to operate on a different directory.\n\n"
        "Examples:\n"
        "  vaultspec-core install\n"
        "  vaultspec-core install --target ./my-project claude\n"
        "  vaultspec-core sync --target ./my-project\n"
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
    from vaultspec_core.cli._target import reset, set_root_target
    from vaultspec_core.logging_config import configure_logging

    log_level = logging.DEBUG if debug else logging.WARNING
    configure_logging(level=log_level, debug=debug)

    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    # Store root-level target for subcommands; no workspace init here.
    # Each subcommand calls apply_target() / apply_target_install() which
    # merges root-level and subcommand-level --target with clear precedence.
    reset()
    set_root_target(target)
    ctx.obj = {}


# ---- Top-level commands ------------------------------------------------------


def _handle_error(exc: Exception) -> None:
    """Convert a domain exception to a CLI error exit."""
    from vaultspec_core.core.exceptions import VaultSpecError

    if isinstance(exc, VaultSpecError):
        typer.echo(f"Error: {exc}", err=True)
        if exc.hint:
            typer.echo(f"  Hint: {exc.hint}", err=True)
        raise typer.Exit(code=1) from exc
    raise exc


@app.command("install")
def cmd_install(
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider to install (all, core, claude, gemini, antigravity, codex)"
        ),
    ] = "all",
    target: TargetOption = None,
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

    Scaffolds the workspace structure and syncs all managed resources.
    Use --upgrade to update builtin rules without re-scaffolding.

    Examples:\n
      vaultspec-core install                       # install all providers in cwd\n
      vaultspec-core install core                  # framework only, no providers\n
      vaultspec-core install claude                # framework + claude\n
      vaultspec-core install --target ./my-project # install in specific directory\n
      vaultspec-core install --upgrade             # update firmware + re-sync\n
      vaultspec-core install claude --dry-run      # preview what would be created\n
    """
    from vaultspec_core.core.commands import install_run
    from vaultspec_core.core.exceptions import VaultSpecError

    path: Path = apply_target_install(target)

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

    try:
        result = install_run(
            path=path, provider=provider, upgrade=upgrade, dry_run=dry_run, force=force
        )
    except VaultSpecError as exc:
        _handle_error(exc)
        return  # unreachable, but satisfies type checker

    # Render result
    from vaultspec_core.console import get_console

    console = get_console()

    if result["action"] == "dry_run":
        from vaultspec_core.cli.rendering import render_dry_run_tree
        from vaultspec_core.core.dry_run import (
            DryRunItem,
            DryRunStatus,
        )

        items = result["items"]
        dry_items = [
            DryRunItem(
                path=str(path / rel).replace("\\", "/"),
                status=(
                    DryRunStatus.EXISTS if (path / rel).exists() else DryRunStatus.NEW
                ),
                label=label,
            )
            for rel, label in items
        ]
        render_dry_run_tree(dry_items, title=f"Install preview → {path}")
    elif result["action"] == "upgrade":
        console.print(f"[bold]Upgraded vaultspec framework at {path}[/bold]")
        seeded = result.get("seeded_count", 0)
        if seeded:
            console.print(f"  Re-seeded [bold]{seeded}[/bold] builtin files.")
        console.print("[bold green]Upgrade complete.[/bold green]")
    else:
        console.print(f"[bold]Installed vaultspec framework to {path}[/bold]")
        items = result.get("items", [])
        for rel, _label in items:
            console.print(f"  {rel}")
        console.print(
            f"Created [bold]{len(items)}[/bold] directories/files. "
            "Run [bold]vaultspec-core sync[/bold] to sync."
        )
        console.print("[bold green]Installation complete.[/bold green]")


@app.command("uninstall")
def cmd_uninstall(
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider to uninstall (all, core, claude, gemini, antigravity, codex)"
        ),
    ] = "all",
    target: TargetOption = None,
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

    Removes all managed artifacts (.vaultspec/, provider dirs, generated configs).
    The .vault/ documentation corpus is preserved by default.
    Use a provider name to remove only that provider's artifacts.

    Examples:\n
      vaultspec-core uninstall                    # remove framework, keep .vault/\n
      vaultspec-core uninstall claude             # remove only claude\n
      vaultspec-core uninstall --target ./proj    # remove from specific directory\n
      vaultspec-core uninstall --remove-vault     # also remove .vault/ docs\n
      vaultspec-core uninstall --dry-run          # preview what would be removed\n
    """
    from vaultspec_core.core.commands import uninstall_run
    from vaultspec_core.core.exceptions import VaultSpecError

    path: Path = apply_target_install(target)

    if not path.exists():
        typer.echo(f"Error: Target directory does not exist: {path}", err=True)
        raise typer.Exit(code=1)

    try:
        result = uninstall_run(
            path=path,
            provider=provider,
            keep_vault=not remove_vault,
            dry_run=dry_run,
            force=force,
        )
    except VaultSpecError as exc:
        _handle_error(exc)
        return

    # Render result
    from vaultspec_core.console import get_console

    console = get_console()
    removed = result.get("removed", [])

    if result["action"] == "dry_run":
        from vaultspec_core.cli.rendering import render_dry_run_tree
        from vaultspec_core.core.dry_run import (
            DryRunItem,
            DryRunStatus,
        )

        dry_items = [
            DryRunItem(path=item_path, status=DryRunStatus.DELETE, label=label)
            for item_path, label in removed
        ]
        render_dry_run_tree(dry_items, title=f"Uninstall preview → {path}")
    elif removed:
        console.print("[bold]Removed vaultspec framework:[/bold]")
        for item_path, _label in removed:
            console.print(f"  {item_path}")
        console.print(f"Removed [bold]{len(removed)}[/bold] items.")
        if result.get("keep_vault"):
            console.print(
                "[dim].vault/ preserved"
                " (pass --remove-vault to also remove"
                " documentation)[/dim]"
            )
    else:
        console.print("Nothing to remove — vaultspec is not installed at this path.")


@app.command("sync")
def cmd_sync(
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider to sync (all, claude, gemini, antigravity, codex)"
        ),
    ] = "all",
    target: TargetOption = None,
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
    apply_target(target)
    if provider == "core":
        typer.echo(
            "Error: 'core' is not a valid sync target. "
            "The sync source is .vaultspec/ (core) itself.",
            err=True,
        )
        raise typer.Exit(code=1)

    from vaultspec_core.core.commands import sync_provider
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.sync import format_summary

    try:
        results = sync_provider(provider, prune=prune, dry_run=dry_run, force=force)
    except VaultSpecError as exc:
        _handle_error(exc)
        return

    from vaultspec_core.console import get_console

    console = get_console()

    if dry_run:
        from vaultspec_core.cli.rendering import render_dry_run_tree
        from vaultspec_core.core import types as _t
        from vaultspec_core.core.dry_run import (
            DryRunItem,
            DryRunStatus,
        )

        action_map = {
            "[ADD]": DryRunStatus.NEW,
            "[UPDATE]": DryRunStatus.UPDATE,
            "[DELETE]": DryRunStatus.DELETE,
        }
        all_items = []
        for r in results:
            for item_path, action in r.items:
                status = action_map.get(action, DryRunStatus.UPDATE)
                all_items.append(
                    DryRunItem(
                        path=item_path,
                        status=status,
                        label=_infer_label(item_path),
                    )
                )
        if all_items:
            title = f"Sync preview → {_t.TARGET_DIR}"
            if provider != "all":
                title = f"Sync preview ({provider}) → {_t.TARGET_DIR}"
            render_dry_run_tree(all_items, title=title)
        else:
            console.print("[dim]Sync preview: no changes[/dim]")
    else:
        # Print sync summaries
        labels = ["Rules", "Skills", "Agents", "System", "Config"]
        for label, r in zip(labels, results, strict=True):
            console.print(f"  [bold]{format_summary(label, r)}[/bold]")

        # Warn if sync produced 0 files
        total_changes = sum(r.added + r.updated for r in results)
        total_skipped = sum(r.skipped for r in results)
        if total_changes == 0 and total_skipped == 0:
            console.print(
                "[bold yellow]Warning:[/bold yellow] Sync produced 0 files. "
                "The .vaultspec/rules/ source directories may be empty.\n"
                "  Run [bold]vaultspec-core install . --upgrade[/bold] "
                "to re-seed builtin content."
            )


def _infer_label(item_path: str) -> str:
    """Infer a human-readable label from a sync output path."""
    p = item_path.replace("\\", "/")

    provider_map = {
        "/.claude/": "claude",
        "/.gemini/": "gemini",
        "/.agents/": "antigravity",
        "/.codex/": "codex",
    }
    provider_name = ""
    for segment, name in provider_map.items():
        if segment in p:
            provider_name = name
            break

    config_map = {
        "/CLAUDE.md": "claude (config)",
        "/GEMINI.md": "gemini (config)",
        "/AGENTS.md": "codex (config)",
        "/config.toml": "codex (config)",
    }
    for suffix, lbl in config_map.items():
        if p.endswith(suffix):
            return lbl

    if "/rules/" in p:
        return f"{provider_name} (rules)" if provider_name else "rules"
    if "/skills/" in p:
        return f"{provider_name} (skills)" if provider_name else "skills"
    if "/agents/" in p:
        return f"{provider_name} (agents)" if provider_name else "agents"
    if "SYSTEM.md" in p or "system" in p.lower():
        return f"{provider_name} (system)" if provider_name else "system"

    return provider_name or ""


# ---- Entry point -------------------------------------------------------------


def run() -> None:
    """CLI entry point for console scripts."""
    app()


if __name__ == "__main__":
    app()
