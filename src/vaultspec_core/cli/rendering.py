"""CLI-layer rendering helpers for dry-run previews and sync summaries.

All Rich/console output for structured previews lives here, not in core.
Key export: :func:`render_dry_run_tree`. Depends on
:mod:`vaultspec_core.core.dry_run` for :class:`~vaultspec_core.core.dry_run.DryRunItem`
and status styles; consumed by :mod:`.root` and indirectly by :mod:`.vault_cmd`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vaultspec_core.console import get_console

if TYPE_CHECKING:
    from collections.abc import Sequence
from vaultspec_core.core.dry_run import (
    STATUS_STYLE,
    DryRunItem,
    DryRunStatus,
    count_by_status,
    group_by_label,
)


def render_dry_run_tree(items: Sequence[DryRunItem], *, title: str = "Preview") -> None:
    """Render a coloured Rich tree of dry-run items to the console.

    Items with a non-empty ``label`` are grouped under a sub-tree branch;
    unlabelled items appear at the root level.  A summary line with
    per-status counts is printed after the tree.

    Status colour coding: ``+`` green (new), ``=`` dim (no change),
    ``~`` yellow (update), ``!`` bold yellow (override), ``-`` red (delete).

    Args:
        items: Sequence of :class:`~vaultspec_core.core.dry_run.DryRunItem`
            to render.
        title: Title displayed at the root node of the tree.
    """
    from rich.tree import Tree

    console = get_console()
    tree = Tree(f"[bold]{title}[/bold]")

    for label, group in group_by_label(list(items)).items():
        branch = tree.add(f"[bold dim]{label}[/bold dim]") if label else tree

        for item in group:
            prefix, colour = STATUS_STYLE[item.status]
            branch.add(f"[{colour}]{prefix} {item.path}[/{colour}]")

    console.print(tree)

    # Summary line
    by_status = count_by_status(list(items))
    parts = []
    for status in DryRunStatus:
        count = by_status.get(status, 0)
        if count:
            prefix, colour = STATUS_STYLE[status]
            parts.append(f"[{colour}]{prefix} {count} {status.value}[/{colour}]")
    if parts:
        console.print("  ".join(parts))


def render_install_summary(
    source_counts: dict[str, int],
    *,
    path: str,
    providers: Sequence[str],
    has_mcp: bool = False,
) -> None:
    """Render a concise post-install summary.

    Shows what was found in the vaultspec source (the actual number of
    rules, skills, and agents the user authored) and which providers
    they were synced to.

    Args:
        source_counts: Mapping of resource type to count, e.g.
            ``{"rules": 1, "skills": 2, "agents": 9}``.
        path: Display path of the installation target.
        providers: Provider names that were enabled (e.g. ``["claude"]``).
        has_mcp: Whether the MCP server configuration was installed.
    """
    from rich.panel import Panel

    console = get_console()

    # --- Header ---
    console.print()
    console.print(
        Panel(
            f"[bold green]Installed[/bold green]  vaultspec\n"
            f"[dim]Target[/dim]     {path}",
            expand=False,
            border_style="green",
        )
    )

    # --- Source resource counts ---
    category_order = ["rules", "skills", "agents"]
    summary_parts: list[str] = []
    for cat in category_order:
        n = source_counts.get(cat, 0)
        if n:
            label = cat if n != 1 else cat.rstrip("s")
            summary_parts.append(f"[bold]{n}[/bold] {label}")

    if summary_parts:
        console.print(f"  Synced {', '.join(summary_parts)}")

    # --- Providers ---
    if providers:
        provider_list = ", ".join(f"[cyan]{p}[/cyan]" for p in providers)
        console.print(f"  Enabled {provider_list}")

    # --- MCP ---
    if has_mcp:
        console.print("  Installed [cyan]MCP server[/cyan]")

    console.print()


def render_uninstall_summary(
    removed: Sequence[tuple[str, str]], *, path: str, keep_vault: bool = True
) -> None:
    """Render a concise post-uninstall summary.

    Args:
        removed: ``(path, label)`` tuples for removed items.
        path: Display path of the uninstall target.
        keep_vault: Whether ``.vault/`` was preserved.
    """
    from rich.panel import Panel

    console = get_console()

    # Extract provider names from labels
    known_providers = {"claude", "gemini", "antigravity", "codex"}
    providers: list[str] = []
    seen: set[str] = set()
    for _, label in removed:
        name = label.split("(")[0].strip().lower() if "(" in label else label.lower()
        if name in known_providers and name not in seen:
            seen.add(name)
            providers.append(name)

    console.print()
    console.print(
        Panel(
            f"[bold red]Uninstalled[/bold red]  vaultspec\n"
            f"[dim]Target[/dim]       {path}",
            expand=False,
            border_style="red",
        )
    )

    if providers:
        provider_list = ", ".join(f"[cyan]{p}[/cyan]" for p in providers)
        console.print(f"  Disabled {provider_list}")

    if keep_vault:
        console.print(
            "  [dim].vault/ preserved"
            "  - pass --remove-vault to also remove documentation[/dim]"
        )
