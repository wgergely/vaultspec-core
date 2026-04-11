"""Root Typer application: global callback, options, and top-level commands.

Mounts :mod:`.vault_cmd` and :mod:`.spec_cmd` sub-groups and defines
``install``, ``uninstall``, and ``sync`` commands that delegate to
:mod:`vaultspec_core.core.commands`. Exposes :func:`run` as the console-script
entry point. Depends on :mod:`vaultspec_core.config.workspace` for workspace
resolution and :mod:`vaultspec_core.core.types` for global path initialization.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from vaultspec_core.core.diagnosis import ProviderDiagnosis, WorkspaceDiagnosis

from vaultspec_core.cli._errors import handle_error as _handle_error
from vaultspec_core.cli._target import (
    TargetOption,
    apply_target,
    apply_target_install,
)

logger = logging.getLogger(__name__)

# Main app definition must precede sub-app imports to enable them to
# reference it if needed (and to satisfy Typer's module-level discovery).
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


# ---- Pre-flight helper -------------------------------------------------------


def _run_preflight(
    target: Path,
    action: str,
    provider: str = "all",
    *,
    force: bool = False,
    dry_run: bool = False,
    scope: str = "framework",
) -> None:
    """Run diagnosis and resolution pre-flight.

    Executes preflight-safe resolution steps (manifest repair, gitignore
    repair, scaffold, adopt) and displays their outcomes. Non-preflight
    steps are shown as informational. Blocks on conflicts unless
    *dry_run* is ``True``.

    Raises :class:`typer.Exit` with code 1 if conflicts are present and
    *dry_run* is ``False``, or if any preflight execution step fails.
    """
    from vaultspec_core.core.diagnosis import diagnose
    from vaultspec_core.core.executor import PREFLIGHT_ACTIONS, execute_plan
    from vaultspec_core.core.resolver import resolve

    try:
        diag = diagnose(target, scope=scope)
    except Exception:
        logger.warning("Pre-flight diagnosis failed", exc_info=True)
        return

    plan = resolve(diag, action, provider, force=force, dry_run=dry_run)

    if not plan.warnings and not plan.conflicts and not plan.steps:
        return

    from vaultspec_core.console import get_console

    console = get_console()

    for warning in plan.warnings:
        console.print(f"  [yellow]![/yellow] {warning}")

    # Execute preflight-safe resolution steps
    if plan.steps and not plan.blocked:
        exec_result = execute_plan(plan, target, dry_run=dry_run)

        for sr in exec_result.results:
            if sr.success:
                console.print(f"  [green]ok[/green] {sr.step.reason}")
            else:
                console.print(f"  [red]FAIL[/red] {sr.step.reason}: {sr.error}")

        if exec_result.failed and not dry_run:
            raise typer.Exit(code=1)

    # Show non-preflight steps as informational (deferred to the main command)
    non_preflight = [s for s in plan.steps if s.action not in PREFLIGHT_ACTIONS]
    for step in non_preflight:
        console.print(
            f"  [dim]>[/dim] {step.reason} (detected, will be addressed by {action})"
        )

    if plan.conflicts:
        console.print()
        for conflict in plan.conflicts:
            console.print(f"  [red]x[/red] {conflict}")
        console.print()
        if not dry_run:
            raise typer.Exit(code=1)


# ---- Top-level commands ------------------------------------------------------


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
    skip: Annotated[
        list[str] | None,
        typer.Option(
            "--skip",
            help="Skip a component (core or provider name). Repeatable.",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Deploy the vaultspec framework to the target directory.

    Scaffolds the workspace structure and syncs all managed resources.
    Use --upgrade to update builtin rules without re-scaffolding.
    Use --skip to exclude components on retry (e.g. --skip core --skip claude).

    Examples:\n
      vaultspec-core install                       # install all providers in cwd\n
      vaultspec-core install core                  # framework only, no providers\n
      vaultspec-core install claude                # framework + claude\n
      vaultspec-core install --target ./my-project # install in specific directory\n
      vaultspec-core install --upgrade             # update firmware + re-sync\n
      vaultspec-core install claude --dry-run      # preview what would be created\n
      vaultspec-core install --skip claude         # install all except claude\n
    """
    from vaultspec_core.core.commands import install_run
    from vaultspec_core.core.exceptions import VaultSpecError

    skip = list(skip or [])
    path: Path = apply_target_install(target)

    # Guard: refuse to create deeply nested paths  - only allow creating the
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

    fw_path = path / ".vaultspec"
    if fw_path.exists() and not fw_path.is_dir():
        typer.echo(
            f"Error: {fw_path} exists but is a file, not a directory.\n"
            "  Remove the file and re-run install.",
            err=True,
        )
        raise typer.Exit(code=1)

    _run_preflight(
        path,
        action="upgrade" if upgrade else "install",
        provider=provider,
        force=force,
        dry_run=dry_run,
        scope="framework",
    )

    try:
        result = install_run(
            path=path,
            provider=provider,
            upgrade=upgrade,
            dry_run=dry_run,
            force=force,
            skip=set(skip),
        )
    except VaultSpecError as exc:
        _handle_error(exc)
        return  # unreachable, but satisfies type checker
    except OSError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None

    if json_output:
        import json

        result["path"] = str(result["path"])
        typer.echo(json.dumps(result, indent=2, default=str))
        raise typer.Exit(0)

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
        from vaultspec_core.cli.rendering import render_install_summary

        render_install_summary(
            result.get("source_counts", {}),
            path=str(path),
            providers=result.get("providers", []),
            has_mcp=result.get("has_mcp", False),
        )


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
    skip: Annotated[
        list[str] | None,
        typer.Option(
            "--skip",
            help="Skip a component (core or provider name). Repeatable.",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Remove the vaultspec framework from the target directory.

    Removes all managed artifacts (.vaultspec/, provider dirs, generated configs).
    The .vault/ documentation corpus is preserved by default.
    Use a provider name to remove only that provider's artifacts.
    Use --skip to exclude components (e.g. --skip claude --skip codex).

    Examples:\n
      vaultspec-core uninstall                    # remove framework, keep .vault/\n
      vaultspec-core uninstall claude             # remove only claude\n
      vaultspec-core uninstall --target ./proj    # remove from specific directory\n
      vaultspec-core uninstall --remove-vault     # also remove .vault/ docs\n
      vaultspec-core uninstall --dry-run          # preview what would be removed\n
      vaultspec-core uninstall --skip codex       # remove all except codex\n
    """
    from vaultspec_core.core.commands import uninstall_run
    from vaultspec_core.core.exceptions import VaultSpecError

    skip = list(skip or [])
    path: Path = apply_target_install(target)

    if not path.exists():
        typer.echo(f"Error: Target directory does not exist: {path}", err=True)
        raise typer.Exit(code=1)

    _run_preflight(
        path,
        action="uninstall",
        provider=provider,
        force=force,
        dry_run=dry_run,
        scope="framework",
    )

    try:
        result = uninstall_run(
            path=path,
            provider=provider,
            keep_vault=not remove_vault,
            dry_run=dry_run,
            force=force,
            skip=set(skip),
        )
    except VaultSpecError as exc:
        _handle_error(exc)
        return
    except OSError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None

    if json_output:
        import json

        result["path"] = str(result["path"])
        typer.echo(json.dumps(result, indent=2, default=str))
        raise typer.Exit(0)

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
        from vaultspec_core.cli.rendering import render_uninstall_summary

        render_uninstall_summary(
            removed, path=str(path), keep_vault=result.get("keep_vault", True)
        )
    else:
        console.print("Nothing to remove  - vaultspec is not installed at this path.")


@app.command("sync")
def cmd_sync(
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider to sync (all, claude, gemini, antigravity, codex)"
        ),
    ] = "all",
    target: TargetOption = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Complete sync: prune stale files and overwrite user-authored content",
        ),
    ] = False,
    skip: Annotated[
        list[str] | None,
        typer.Option(
            "--skip",
            help="Skip a component (core or provider name). Repeatable.",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Sync rules, skills, agents, configs, and system prompts.

    By default sync is non-destructive: missing files are added and changed
    files are updated, but stale destination files and user-authored
    system/config files are left untouched (with warnings).

    Use --force for a complete sync that prunes stale files and overwrites
    user-authored content to match the .vaultspec/ source exactly.

    Defaults to syncing all providers. Pass a provider name to sync only
    that provider (e.g. 'vaultspec-core sync claude').
    Use --skip to exclude providers (e.g. --skip claude --skip codex).
    """
    skip = list(skip or [])
    apply_target(target, split_source=True)
    if provider == "core":
        typer.echo(
            "Error: 'core' is not a valid sync target. "
            "The sync source is .vaultspec/ (core) itself.\n"
            "  Hint: use 'vaultspec-core sync all' to sync all providers, "
            "or 'vaultspec-core install --upgrade' to update the framework.",
            err=True,
        )
        raise typer.Exit(code=1)

    from vaultspec_core.core.types import get_context

    try:
        ctx = get_context()
        sync_target = ctx.target_dir
    except LookupError:
        sync_target = target or Path.cwd()

    _run_preflight(
        sync_target,
        action="sync",
        provider=provider,
        force=force,
        dry_run=dry_run,
        scope="sync",
    )

    from vaultspec_core.core.commands import sync_provider
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        results = sync_provider(provider, dry_run=dry_run, force=force, skip=set(skip))
    except VaultSpecError as exc:
        _handle_error(exc)
        return
    except OSError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None

    if json_output:
        import dataclasses
        import json

        data = [dataclasses.asdict(r) for r in results]
        typer.echo(json.dumps(data, indent=2, default=str))
        raise typer.Exit(0)

    from vaultspec_core.console import get_console

    console = get_console()

    if dry_run:
        from vaultspec_core.cli.rendering import render_dry_run_tree
        from vaultspec_core.core.dry_run import (
            DryRunItem,
            DryRunStatus,
        )
        from vaultspec_core.core.types import get_context

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
            _target_dir = get_context().target_dir
            title = f"Sync preview → {_target_dir}"
            if provider != "all":
                title = f"Sync preview ({provider}) → {_target_dir}"
            render_dry_run_tree(all_items, title=title)
        else:
            console.print("[dim]Sync preview: no changes[/dim]")
    else:
        from vaultspec_core.core.manifest import installed_tool_configs
        from vaultspec_core.core.types import SyncResult

        active_names = [cfg.name for cfg in installed_tool_configs().values()]

        # Header
        provider_list = ", ".join(f"[cyan]{n}[/cyan]" for n in active_names)
        console.print(
            f"Syncing [bold]{len(active_names)}[/bold] enabled "
            f"providers ({provider_list})...\n"
        )

        # Collect per-tool results across all 5 resource passes
        resource_labels = ["rules", "skills", "agents", "system", "config"]
        tool_resources: dict[str, list[tuple[str, SyncResult]]] = {}
        for label, r in zip(resource_labels, results, strict=True):
            for tool_name, tool_result in r.per_tool.items():
                tool_resources.setdefault(tool_name, []).append((label, tool_result))

        # Render one line per provider
        for tool_name in active_names:
            entries = tool_resources.get(tool_name, [])
            parts: list[str] = []
            for res_label, tr in entries:
                if tr.added:
                    parts.append(f"{tr.added} {res_label} added")
                if tr.updated:
                    parts.append(f"{tr.updated} {res_label} updated")
                if tr.pruned:
                    parts.append(f"{tr.pruned} {res_label} pruned")

            if parts:
                detail = ", ".join(parts)
                console.print(f"  [bold]{tool_name:<16}[/bold] {detail}")
            else:
                console.print(
                    f"  [green]\u2713[/green] [dim]{tool_name:<16} up to date[/dim]"
                )

        # Check if bundled builtins are newer than deployed
        from vaultspec_core.builtins import check_outdated

        vaultspec_rules = sync_target / ".vaultspec" / "rules"
        outdated = check_outdated(vaultspec_rules) if vaultspec_rules.is_dir() else []
        if outdated:
            console.print()
            console.print(
                f"[bold yellow]Upgrade available:[/bold yellow] "
                f"{len(outdated)} builtin(s) in the installed "
                f"vaultspec-core package are newer than .vaultspec/:"
            )
            for path in outdated:
                console.print(f"  [yellow]•[/yellow] {path}")
            console.print(
                "\n  Run [bold]vaultspec-core install --upgrade[/bold] "
                "to update, then [bold]sync[/bold] again."
            )

        # Collect and display warnings from all sync passes
        all_warnings = [w for r in results for w in r.warnings]
        if all_warnings:
            console.print()
            console.print(
                f"[bold yellow]Warning:[/bold yellow] "
                f"{len(all_warnings)} item(s) differ from .vaultspec/ source. "
                f"Use [bold]--force[/bold] to resolve:"
            )
            for warning in all_warnings:
                console.print(f"  [yellow]•[/yellow] {warning}")

        # Collect and display errors from all sync passes
        all_errors = []
        for r in results:
            all_errors.extend(r.errors)
        if all_errors:
            console.print(f"\n  [red]Errors ({len(all_errors)}):[/red]")
            for err in all_errors:
                console.print(f"    [red]x[/red] {err}")
            raise typer.Exit(code=1)

        # Warn if sync produced 0 files
        total_changes = sum(r.added + r.updated for r in results)
        total_skipped = sum(r.skipped for r in results)
        if total_changes == 0 and total_skipped == 0 and not all_warnings:
            console.print(
                "\n[bold yellow]Warning:[/bold yellow] Sync produced 0 files. "
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


@app.command("doctor")
def cmd_doctor(
    target: TargetOption = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output diagnosis as JSON")
    ] = False,
    debug: Annotated[
        bool, typer.Option("--debug", "-d", help="Enable debug logging")
    ] = False,
) -> None:
    """Diagnose workspace health and report issues.

    Runs all diagnostic collectors and reports the state of the framework,
    providers, builtins, gitignore, and configuration files.

    Exit codes: 0 = all ok, 1 = warnings, 2 = errors.

    Examples:\n
      vaultspec-core doctor                        # diagnose current directory\n
      vaultspec-core doctor --target ./my-project  # diagnose specific directory\n
      vaultspec-core doctor --json                 # machine-readable output\n
    """
    import dataclasses
    import json

    # Initialize workspace context so collectors can read tool configs.
    try:
        apply_target(target)
    except Exception:
        logger.debug("Could not initialize workspace context", exc_info=True)

    from vaultspec_core.core.diagnosis import (
        BuiltinVersionSignal,
        ConfigSignal,
        ContentSignal,
        FrameworkSignal,
        GitattributesSignal,
        GitignoreSignal,
        ManifestEntrySignal,
        PrecommitSignal,
        diagnose,
    )

    effective = target or Path.cwd()
    effective = effective.resolve()

    if not effective.exists():
        typer.echo(
            f"Error: target directory does not exist: {effective}",
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        diag = diagnose(effective, scope="full")
    except Exception as exc:
        typer.echo(f"Error: diagnosis failed: {exc}", err=True)
        raise typer.Exit(code=2) from None

    if json_output:
        data = dataclasses.asdict(diag)
        typer.echo(json.dumps(data, indent=2, default=str))
        exit_code = _doctor_exit_code(diag)
        raise typer.Exit(code=exit_code)

    from rich.table import Table

    from vaultspec_core.console import get_console

    console = get_console()
    table = Table(show_header=True, show_edge=False, pad_edge=False)
    table.add_column("Component", style="bold", min_width=16)
    table.add_column("Status", min_width=8)
    table.add_column("Detail")

    # Framework row
    fw_status, fw_style = _signal_status(
        diag.framework,
        {
            FrameworkSignal.PRESENT: ("ok", "green"),
            FrameworkSignal.MISSING: ("error", "red"),
            FrameworkSignal.CORRUPTED: ("error", "red"),
        },
    )
    fw_detail = {
        FrameworkSignal.PRESENT: ".vaultspec/ present",
        FrameworkSignal.MISSING: ".vaultspec/ not found",
        FrameworkSignal.CORRUPTED: ".vaultspec/ corrupted manifest",
    }.get(diag.framework, str(diag.framework))
    table.add_row("framework", f"[{fw_style}]{fw_status}[/{fw_style}]", fw_detail)

    # Provider rows
    for tool, prov in diag.providers.items():
        prov_status, prov_style = _provider_status(prov)
        details = []
        details.append(f"dir: {prov.dir_state.value}")
        if prov.manifest_entry not in (
            ManifestEntrySignal.COHERENT,
            ManifestEntrySignal.NOT_INSTALLED,
        ):
            details.append(f"manifest: {prov.manifest_entry.value}")
        if prov.config not in (ConfigSignal.OK,):
            details.append(f"config: {prov.config.value}")
        stale = sum(1 for s in prov.content.values() if s != ContentSignal.CLEAN)
        if stale:
            details.append(f"{stale} file(s) need attention")
        table.add_row(
            tool.value,
            f"[{prov_style}]{prov_status}[/{prov_style}]",
            ", ".join(details),
        )

    # Builtins row
    bv_status, bv_style = _signal_status(
        diag.builtin_version,
        {
            BuiltinVersionSignal.CURRENT: ("ok", "green"),
            BuiltinVersionSignal.MODIFIED: ("warn", "yellow"),
            BuiltinVersionSignal.DELETED: ("error", "red"),
            BuiltinVersionSignal.NO_SNAPSHOTS: ("info", "dim"),
        },
    )
    table.add_row(
        "builtins",
        f"[{bv_style}]{bv_status}[/{bv_style}]",
        diag.builtin_version.value,
    )

    # Gitignore row
    gi_status, gi_style = _signal_status(
        diag.gitignore,
        {
            GitignoreSignal.COMPLETE: ("ok", "green"),
            GitignoreSignal.PARTIAL: ("warn", "yellow"),
            GitignoreSignal.NO_ENTRIES: ("info", "dim"),
            GitignoreSignal.NO_FILE: ("info", "dim"),
            GitignoreSignal.CORRUPTED: ("error", "red"),
        },
    )
    table.add_row(
        "gitignore",
        f"[{gi_style}]{gi_status}[/{gi_style}]",
        diag.gitignore.value,
    )

    # Gitattributes row
    ga_status, ga_style = _signal_status(
        diag.gitattributes,
        {
            GitattributesSignal.COMPLETE: ("ok", "green"),
            GitattributesSignal.PARTIAL: ("warn", "yellow"),
            GitattributesSignal.NO_ENTRIES: ("info", "dim"),
            GitattributesSignal.NO_FILE: ("info", "dim"),
            GitattributesSignal.CORRUPTED: ("error", "red"),
        },
    )
    table.add_row(
        "gitattributes",
        f"[{ga_style}]{ga_status}[/{ga_style}]",
        diag.gitattributes.value,
    )

    # MCP row
    mcp_status, mcp_style = _signal_status(
        diag.mcp,
        {
            ConfigSignal.OK: ("ok", "green"),
            ConfigSignal.MISSING: ("warn", "yellow"),
            ConfigSignal.FOREIGN: ("info", "dim"),
        },
    )
    mcp_detail = {
        ConfigSignal.OK: ".mcp.json present",
        ConfigSignal.MISSING: ".mcp.json not found",
        ConfigSignal.FOREIGN: ".mcp.json present (no vaultspec entry)",
    }.get(diag.mcp, str(diag.mcp))
    table.add_row(
        "mcp",
        f"[{mcp_style}]{mcp_status}[/{mcp_style}]",
        mcp_detail,
    )

    # Pre-commit row
    pc_status, pc_style = _signal_status(
        diag.precommit,
        {
            PrecommitSignal.COMPLETE: ("ok", "green"),
            PrecommitSignal.INCOMPLETE: ("warn", "yellow"),
            PrecommitSignal.NON_CANONICAL: ("warn", "yellow"),
            PrecommitSignal.NO_HOOKS: ("warn", "yellow"),
            PrecommitSignal.NO_FILE: ("info", "dim"),
        },
    )
    pc_detail = {
        PrecommitSignal.COMPLETE: "all hooks present",
        PrecommitSignal.INCOMPLETE: "missing canonical hooks",
        PrecommitSignal.NON_CANONICAL: "non-canonical entry pattern",
        PrecommitSignal.NO_HOOKS: "no vaultspec hooks found",
        PrecommitSignal.NO_FILE: "no .pre-commit-config.yaml",
    }.get(diag.precommit, str(diag.precommit))
    table.add_row(
        "precommit",
        f"[{pc_style}]{pc_status}[/{pc_style}]",
        pc_detail,
    )

    console.print(table)

    exit_code = _doctor_exit_code(diag)
    raise typer.Exit(code=exit_code)


def _signal_status(
    signal: object,
    mapping: dict,
) -> tuple[str, str]:
    """Map a signal value to a (status_label, style) pair."""
    val = signal.value if hasattr(signal, "value") else signal
    return mapping.get(signal, (f"unknown ({val})", "dim"))


def _provider_status(prov: ProviderDiagnosis) -> tuple[str, str]:
    """Derive aggregate status for a provider diagnosis."""
    from vaultspec_core.core.diagnosis import (
        ContentSignal,
        ManifestEntrySignal,
        ProviderDirSignal,
    )

    if prov.manifest_entry == ManifestEntrySignal.NOT_INSTALLED:
        return ("skip", "dim")

    error_signals = (
        prov.manifest_entry == ManifestEntrySignal.ORPHANED,
        prov.dir_state == ProviderDirSignal.MISSING,
    )
    if any(error_signals):
        return ("error", "red")

    warn_signals = (
        prov.dir_state in (ProviderDirSignal.PARTIAL, ProviderDirSignal.MIXED),
        prov.manifest_entry == ManifestEntrySignal.UNTRACKED,
        any(s != ContentSignal.CLEAN for s in prov.content.values()),
    )
    if any(warn_signals):
        return ("warn", "yellow")

    return ("ok", "green")


def _doctor_exit_code(diag: WorkspaceDiagnosis) -> int:
    """Compute the doctor exit code from a diagnosis.

    Returns:
        ``0`` if all ok/info, ``1`` if any warnings, ``2`` if any errors.
    """
    from vaultspec_core.core.diagnosis import (
        BuiltinVersionSignal,
        ConfigSignal,
        ContentSignal,
        FrameworkSignal,
        GitattributesSignal,
        GitignoreSignal,
        ManifestEntrySignal,
        PrecommitSignal,
        ProviderDirSignal,
    )

    has_error = False
    has_warn = False

    if diag.framework in (FrameworkSignal.MISSING, FrameworkSignal.CORRUPTED):
        has_error = True
    if diag.gitignore == GitignoreSignal.CORRUPTED:
        has_error = True
    if diag.gitattributes == GitattributesSignal.CORRUPTED:
        has_error = True
    if diag.precommit in (
        PrecommitSignal.INCOMPLETE,
        PrecommitSignal.NON_CANONICAL,
        PrecommitSignal.NO_HOOKS,
    ):
        has_warn = True
    if diag.builtin_version == BuiltinVersionSignal.DELETED:
        has_error = True
    if diag.builtin_version == BuiltinVersionSignal.MODIFIED:
        has_warn = True

    for prov in diag.providers.values():
        if prov.manifest_entry == ManifestEntrySignal.NOT_INSTALLED:
            continue
        if prov.manifest_entry == ManifestEntrySignal.ORPHANED:
            has_error = True
        if prov.manifest_entry == ManifestEntrySignal.UNTRACKED:
            has_warn = True
        if prov.dir_state == ProviderDirSignal.MISSING:
            has_error = True
        if prov.dir_state == ProviderDirSignal.MIXED:
            has_warn = True
        if prov.dir_state in (ProviderDirSignal.EMPTY, ProviderDirSignal.PARTIAL):
            has_warn = True
        if prov.config in (ConfigSignal.MISSING, ConfigSignal.FOREIGN):
            has_warn = True
        for s in prov.content.values():
            if s in (ContentSignal.STALE, ContentSignal.DIVERGED):
                has_warn = True
            if s == ContentSignal.MISSING:
                has_warn = True

    if has_error:
        return 2
    if has_warn:
        return 1
    return 0


def _register_subcommands() -> None:
    """Mount sub-apps with deferred imports to avoid circular dependencies."""
    from .spec_cmd import spec_app
    from .vault_cmd import vault_app

    app.add_typer(vault_app, name="vault")
    app.add_typer(spec_app, name="spec")


_register_subcommands()


# ---- Entry point -------------------------------------------------------------


def run() -> None:
    """CLI entry point for console scripts."""
    app()


if __name__ == "__main__":
    run()
