"""Rich tree renderer for dry-run previews.

Used by install --dry-run and uninstall --dry-run to display a coloured,
categorized tree of filesystem changes.
"""

from __future__ import annotations

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


def render_dry_run_tree(items: list[DryRunItem], *, title: str = "Preview") -> None:
    """Render a coloured tree of dry-run items to the console.

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
    for item in items:
        prefix, colour = _STATUS_STYLE[item.status]
        tree.add(f"[{colour}]{prefix} {item.path}[/{colour}]")
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
