"""``vaultspec-core sync``.

Defines :func:`cmd_sync`, mounted by :mod:`vaultspec_core.cli.root` as the
``sync`` command on :data:`~vaultspec_core.cli.root_app.app`. Also hosts the
sync-specific rendering and outcome-collection helpers
(:func:`collect_sync_outcomes` and friends), some of which are re-exported
from :mod:`vaultspec_core.cli.root` for use by tests.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 - Typer evaluates the --target annotation.
from typing import TYPE_CHECKING, Annotated, Any

import typer

from vaultspec_core.cli._errors import handle_error as _handle_error
from vaultspec_core.cli._target import (
    TargetOption,
    apply_target,
    resolve_effective_target,
)
from vaultspec_core.cli.json_output import json_format_kwargs
from vaultspec_core.cli.root_preflight import run_preflight
from vaultspec_core.core.enums import CliAction

if TYPE_CHECKING:
    from rich.console import Console

    from vaultspec_core.cli.rendering import OutcomeItem
    from vaultspec_core.core.enums import Tool
    from vaultspec_core.core.types import SyncResult


def reject_core_sync_target(provider: str) -> None:
    """Refuse ``core`` as a sync target; it is not a provider output.

    Raises:
        typer.Exit: Code 1, when ``provider`` is ``"core"``.
    """
    if provider != "core":
        return
    typer.echo(
        "Error: 'core' is not a valid sync target. "
        "The sync source is .vaultspec/ (core) itself.\n"
        "  Hint: use 'vaultspec-core sync all' to sync all providers, "
        "or 'vaultspec-core install --upgrade' to update the framework.",
        err=True,
    )
    raise typer.Exit(code=1)


def render_sync_dry_run(
    results: list[SyncResult],
    provider: str,
    skip: list[str],
    json_output: bool,
    console: Console,
) -> None:
    """Render a sync ``--dry-run`` preview and exit.

    Args:
        results: Per-provider sync results collected in preview mode.
        provider: The provider argument as passed to ``cmd_sync``.
        skip: Components excluded from the sync, as passed to ``cmd_sync``.
        json_output: Whether to emit the machine-readable JSON envelope.
        console: The Rich console to render human-readable output to.

    Raises:
        typer.Exit: Always; a dry run never falls through to a live sync.
    """
    if json_output:
        import json

        from vaultspec_core.cli.rendering import json_envelope, outcomes_as_json

        outcomes = collect_sync_outcomes(results, provider, skip)
        inner = outcomes_as_json(outcomes)
        envelope = json_envelope(
            "sync", str(inner["status"]), {"items": inner["items"]}
        )
        typer.echo(json.dumps(envelope, **json_format_kwargs()))
        raise typer.Exit(0)

    from vaultspec_core.cli.rendering import render_dry_run_tree
    from vaultspec_core.core.dry_run import DryRunItem, DryRunStatus
    from vaultspec_core.core.types import get_context

    action_map = {
        "[ADD]": DryRunStatus.NEW,
        "[UPDATE]": DryRunStatus.UPDATE,
        "[UNCHANGED]": DryRunStatus.EXISTS,
        "[SKIP]": DryRunStatus.EXISTS,
        "[DELETE]": DryRunStatus.DELETE,
    }
    all_items = [
        DryRunItem(
            path=item_path,
            status=action_map.get(action, DryRunStatus.UPDATE),
            label=infer_label(item_path),
        )
        for r in results
        for item_path, action in r.items
    ]
    if not all_items:
        console.print("[dim]Sync preview: no changes[/dim]")
        raise typer.Exit(0)

    target_dir = get_context().target_dir
    title = f"Sync preview -> {target_dir}"
    if provider != "all":
        title = f"Sync preview ({provider}) -> {target_dir}"
    render_dry_run_tree(all_items, title=title)
    raise typer.Exit(0)


def resolve_active_sync_names(
    active_configs: dict[Tool, Any], provider: str, skip: list[str]
) -> list[str]:
    """Return the enabled provider config names selected for this sync.

    Args:
        active_configs: Mapping of provider tool to its installed config, as
            returned by :func:`~vaultspec_core.core.manifest.installed_tool_configs`.
        provider: The provider argument as passed to ``cmd_sync``.
        skip: Components excluded from the sync, as passed to ``cmd_sync``.

    Returns:
        The config names selected by ``provider`` and not excluded by ``skip``.
    """
    if provider == "all":
        return [
            cfg.name
            for tool, cfg in active_configs.items()
            if tool.value not in skip and cfg.name not in skip
        ]
    return [
        cfg.name
        for tool, cfg in active_configs.items()
        if (tool.value == provider or cfg.name == provider)
        and tool.value not in skip
        and cfg.name not in skip
    ]


def render_sync_post_notices(
    console: Console,
    sync_target: Path,
    results: list[SyncResult],
    all_warnings: list[str],
    code: int,
    active_names: list[str],
) -> None:
    """Render the advisory notices shown after a non-JSON, non-dry-run sync.

    Covers three independent notices: builtins newer than ``.vaultspec/``,
    provider-content warnings that ``--force`` would resolve, and a
    zero-files-produced warning for an otherwise clean run.

    Args:
        console: The Rich console to render to.
        sync_target: The resolved sync target directory.
        results: Per-provider sync results from the live sync pass.
        all_warnings: Warnings collected across ``results``.
        code: The exit code ``emit_outcomes`` computed for the sync.
        active_names: The provider config names selected for this sync.
    """
    from vaultspec_core.builtins import check_outdated

    vaultspec_dir = sync_target / ".vaultspec"
    outdated = check_outdated(vaultspec_dir) if vaultspec_dir.is_dir() else []
    if outdated:
        console.print()
        console.print(
            f"[bold yellow]Upgrade available:[/bold yellow] "
            f"{len(outdated)} builtin(s) in the installed "
            f"vaultspec-core package are newer than .vaultspec/:"
        )
        for path in outdated:
            console.print(f"  [yellow]-[/yellow] {path}")
        from vaultspec_core.cli.rendering import hints_suppressed, render_next_actions

        if not hints_suppressed():
            render_next_actions(
                [
                    (
                        "Update builtins to the packaged version",
                        "vaultspec-core install --upgrade",
                    ),
                    ("Re-sync after upgrading", "vaultspec-core sync"),
                ]
            )

    if all_warnings:
        console.print()
        console.print(
            f"[bold yellow]Warning:[/bold yellow] "
            f"{len(all_warnings)} item(s) differ from .vaultspec/ source. "
            f"Use [bold]--force[/bold] to resolve:"
        )
        for warning in all_warnings:
            console.print(f"  [yellow]-[/yellow] {warning}")

    # Warn only when a clean run genuinely found nothing to project.
    total_changes = sum(r.added + r.updated for r in results)
    total_skipped = sum(r.skipped for r in results)
    total_unchanged = sum(r.unchanged for r in results)
    ran_clean = code == 0 and not all_warnings
    projected_nothing = (
        total_changes == 0 and total_skipped == 0 and total_unchanged == 0
    )
    if not (ran_clean and active_names and projected_nothing):
        return

    console.print(
        "\n[bold yellow]Warning:[/bold yellow] Sync produced 0 files. "
        "The .vaultspec/ source directories may be empty."
    )
    from vaultspec_core.cli.rendering import hints_suppressed, render_next_actions

    if not hints_suppressed():
        render_next_actions(
            [("Re-seed builtin content", "vaultspec-core install --upgrade")]
        )


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
            help=(
                "Skip a component: core, a provider name, mcp, or "
                "precommit. Repeatable."
            ),
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Sync rules, skills, agents, configs, system prompts, and MCPs.

    This is the authoritative complete sync from .vaultspec/ to enrolled
    provider outputs. By default sync is non-destructive: missing files are
    added and changed files are updated, but stale destination files and
    user-authored system/config files are left untouched (with warnings).

    Use --force for a complete sync that prunes stale files and overwrites
    user-authored content to match the .vaultspec/ source exactly.

    Defaults to syncing all providers. Pass a provider name to sync only
    that provider (e.g. 'vaultspec-core sync claude').
    Use --skip to exclude components (e.g. --skip claude --skip precommit);
    valid targets are core, provider names, mcp, and precommit.
    """
    skip = list(skip or [])
    apply_target(target, split_source=True, json_output=json_output)
    reject_core_sync_target(provider)

    from vaultspec_core.core.types import get_context

    try:
        ctx = get_context()
        sync_target = ctx.target_dir
    except LookupError:
        sync_target = resolve_effective_target(target)

    run_preflight(
        sync_target,
        action=CliAction.SYNC,
        provider=provider,
        force=force,
        dry_run=dry_run,
        scope="sync",
        render=not json_output,
        skip=set(skip),
    )

    # The all-provider sync is the one CLI path that fires the ``config.synced``
    # lifecycle event, so it is the one that must offer the operator the choice
    # before a workspace hook's shell command could run (GHSA-w5xf-54cr-fxcq).
    # Declining, or having no operator to ask, only costs the hooks: the sync
    # itself is a legitimate operation and still completes.
    if provider == "all" and not dry_run and "hooks" not in skip:
        from vaultspec_core.cli._hook_trust import consent_gate
        from vaultspec_core.core.provider_sync import target_hooks_dir

        # The same resolver the firing code uses, deliberately. Under
        # ``--target`` the ambient context still reflects the CWD/source split,
        # so resolving the directory any other way here would offer the
        # operator the CWD workspace's hooks while the target workspace's were
        # the ones about to run.
        consent_gate(
            "config.synced",
            json_output=json_output,
            hooks_dir=target_hooks_dir(sync_target),
        )

    from vaultspec_core.core.commands import sync_provider
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        results = sync_provider(provider, dry_run=dry_run, force=force, skip=set(skip))
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc, json_output=json_output)
        return

    from vaultspec_core.console import get_console

    console = get_console()

    if dry_run:
        render_sync_dry_run(results, provider, skip, json_output, console)

    # Non-dry-run: route every provider through the canonical outcome
    # renderer. Per the cli-sync-vocabulary ADR (audit findings
    # S2/S8/S10/S19), one helper feeds text and JSON from a single
    # OutcomeItem list, and each provider becomes a group so the output
    # stays per-provider readable without a bespoke summary loop.
    from vaultspec_core.cli.rendering import emit_outcomes
    from vaultspec_core.core.manifest import installed_tool_configs

    active_configs = installed_tool_configs()
    active_names = resolve_active_sync_names(active_configs, provider, skip)

    # The zero-enrolment notice short-circuits past `emit_outcomes`, which is
    # also the only thing that computes the exit code - so taking it while a
    # pass has already failed reports success for a run that did not succeed
    # (issue #417). Whether that was reachable was long unclear, because every
    # *resource* pass filters by the enrolled set before doing work and so
    # fails at nothing when nothing is enrolled. The provider-hooks pass does
    # not: it loads the workspace's canonical hook sources first and only then
    # asks which providers want them, so an undecodable hook file fails before
    # enrolment is ever consulted. The notice itself stays true either way and
    # is still worth printing; only the unconditional success is withdrawn.
    if not active_names and not json_output:
        console.print("[dim]No enabled providers to sync.[/dim]")
        if not any(r.errors for r in results):
            raise typer.Exit(0)

    outcomes = collect_sync_outcomes(results, provider, skip)

    all_warnings = [w for r in results for w in r.warnings]
    extra_json = {"warnings": all_warnings} if all_warnings else None
    code = emit_outcomes(
        outcomes,
        command="sync",
        title="Sync",
        json_output=json_output,
        extra_json=extra_json,
    )

    if not json_output:
        render_sync_post_notices(
            console, sync_target, results, all_warnings, code, active_names
        )

    raise typer.Exit(code)


def collect_sync_outcomes(
    results: list[SyncResult], provider: str, skip: list[str]
) -> list[OutcomeItem]:
    """Flatten sync-pass results into per-provider-grouped outcomes.

    Each resource pass carries per-provider results in ``per_tool`` when its
    output is host-specific; global passes use their resource label. Shared by
    the text and ``--json`` renderings of both ``sync`` and ``sync --dry-run``
    so the surfaces cannot drift apart.
    """
    from vaultspec_core.cli.rendering import sync_outcomes

    labels = ["rules", "skills", "agents", "system", "config"]
    if provider == "all" and "mcp" not in skip:
        labels.append("mcps")
    if "hooks" not in skip:
        labels.append("hooks")
    outcomes: list[OutcomeItem] = []
    # Results beyond the known positional resource passes (e.g. the trailing
    # structural-backfill pass, issue #133) are grouped per inferred provider so
    # the surface never crashes on a length mismatch and still reports them.
    for index, r in enumerate(results):
        label = labels[index] if index < len(labels) else None
        if r.per_tool:
            for tool_name, tool_result in r.per_tool.items():
                outcomes.extend(sync_outcomes(tool_result, group=tool_name))
        elif label is not None:
            outcomes.extend(sync_outcomes(r, group=label))
        else:
            for item_path, _action in r.items:
                outcomes.extend(
                    sync_outcomes(
                        single_item_result(r, item_path),
                        group=infer_label(item_path),
                    )
                )
    return outcomes


def single_item_result(source: SyncResult, item_path: str) -> SyncResult:
    """Return a one-item SyncResult mirroring ``item_path``'s action.

    Used to re-group structural-backfill items under their inferred provider
    label without mutating the original aggregate result.
    """
    from vaultspec_core.core.types import SyncResult as _SyncResult

    single = _SyncResult()
    for path, action in source.items:
        if path != item_path:
            continue
        single.items.append((path, action))
        if action == "[ADD]":
            single.added += 1
        elif action == "[UPDATE]":
            single.updated += 1
        elif action == "[DELETE]":
            single.pruned += 1
    return single


def infer_label(item_path: str) -> str:
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
