"""Dry-run preview data models.

Provides status enums and item dataclasses used by install/uninstall/sync
--dry-run flows. Rendering is handled by the CLI layer.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum


class DryRunStatus(StrEnum):
    """Status categories for dry-run items.

    Attributes:
        NEW: File will be created at the destination.
        EXISTS: File already exists and content is unchanged.
        UPDATE: File already exists and will be overwritten.
        OVERRIDE: Managed builtin file overridden by user content.
        DELETE: Stale destination file will be removed.
    """

    NEW = "new"
    EXISTS = "exists"
    UPDATE = "update"
    OVERRIDE = "override"
    DELETE = "delete"


STATUS_STYLE: dict[DryRunStatus, tuple[str, str]] = {
    DryRunStatus.NEW: ("+", "green"),
    DryRunStatus.EXISTS: ("=", "dim"),
    DryRunStatus.UPDATE: ("~", "yellow"),
    DryRunStatus.OVERRIDE: ("!", "bold yellow"),
    DryRunStatus.DELETE: ("-", "red"),
}


@dataclass
class DryRunItem:
    """A single item in a dry-run preview.

    Attributes:
        path: Destination file path (forward-slash normalised).
        status: Planned action for this file.
        label: Category label grouping related items (e.g. ``"claude/rules"``,
            ``"core"``, ``"config"``).  Empty string means no grouping.
    """

    path: str
    status: DryRunStatus
    label: str = ""


def group_by_label(items: list[DryRunItem]) -> dict[str, list[DryRunItem]]:
    """Group items by label, preserving insertion order.

    Args:
        items: Flat list of :class:`DryRunItem` instances.

    Returns:
        Ordered mapping of label string to its constituent items.  Items
        with an empty label are grouped under the ``""`` key.
    """
    groups: dict[str, list[DryRunItem]] = defaultdict(list)
    for item in items:
        groups[item.label].append(item)
    return groups


def count_by_status(items: list[DryRunItem]) -> dict[DryRunStatus, int]:
    """Return counts of items grouped by status.

    Args:
        items: Flat list of :class:`DryRunItem` instances.

    Returns:
        Mapping of each :class:`DryRunStatus` present in *items* to its
        occurrence count.
    """
    by_status: dict[DryRunStatus, int] = {}
    for item in items:
        by_status[item.status] = by_status.get(item.status, 0) + 1
    return by_status
