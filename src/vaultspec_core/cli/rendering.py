"""CLI-layer rendering helpers for dry-run previews and sync summaries.

All Rich/console output lives here, not in core/.
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
