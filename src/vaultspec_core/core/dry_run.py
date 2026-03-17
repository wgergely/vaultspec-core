"""Rich tree renderer for dry-run previews.

Used by install --dry-run and uninstall --dry-run to display a coloured,
categorized tree of filesystem changes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from rich.tree import Tree

from vaultspec_core.console import get_console


class DryRunStatus(StrEnum):
    """Status categories for dry-run items."""

    NEW = "new"
    EXISTS = "exists"
    UPDATE = "update"
    OVERRIDE = "override"
    DELETE = "delete"


_STATUS_STYLE: dict[DryRunStatus, tuple[str, str]] = {
    DryRunStatus.NEW: ("+", "green"),
    DryRunStatus.EXISTS: ("=", "dim"),
    DryRunStatus.UPDATE: ("~", "yellow"),
    DryRunStatus.OVERRIDE: ("!", "bold yellow"),
    DryRunStatus.DELETE: ("-", "red"),
}


@dataclass
class DryRunItem:
    """A single item in a dry-run preview."""

    path: str
    status: DryRunStatus
    label: str = ""
    """Category label (e.g. 'claude/rules', 'core', 'config')."""


def render_dry_run_tree(items: list[DryRunItem], *, title: str = "Preview") -> None:
    """Render a coloured tree of dry-run items to the console.

    Items with a ``label`` are grouped under that label as a sub-tree.
    Items without a label appear at the root level.

    Colour coding:
    - green (+) = new
    - dim (=) = already exists, no change
    - yellow (~) = will be updated
    - bold yellow (!) = will be overridden
    - red (-) = will be deleted
    """
    console = get_console()
    tree = Tree(f"[bold]{title}[/bold]")

    by_status: dict[DryRunStatus, int] = {}

    # Group items by label, preserving insertion order
    groups: dict[str, list[DryRunItem]] = defaultdict(list)
    for item in items:
        groups[item.label].append(item)

    for label, group in groups.items():
        branch = tree.add(f"[bold dim]{label}[/bold dim]") if label else tree

        for item in group:
            prefix, colour = _STATUS_STYLE[item.status]
            branch.add(f"[{colour}]{prefix} {item.path}[/{colour}]")
            by_status[item.status] = by_status.get(item.status, 0) + 1

    console.print(tree)

    # Summary line
    parts = []
    for status in DryRunStatus:
        count = by_status.get(status, 0)
        if count:
            prefix, colour = _STATUS_STYLE[status]
            parts.append(f"[{colour}]{prefix} {count} {status.value}[/{colour}]")
    if parts:
        console.print("  ".join(parts))
