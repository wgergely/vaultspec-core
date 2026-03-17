"""Dry-run preview data models.

Provides status enums and item dataclasses used by install/uninstall/sync
--dry-run flows. Rendering is handled by the CLI layer.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum


class DryRunStatus(StrEnum):
    """Status categories for dry-run items."""

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
    """A single item in a dry-run preview."""

    path: str
    status: DryRunStatus
    label: str = ""
    """Category label (e.g. 'claude/rules', 'core', 'config')."""


def group_by_label(items: list[DryRunItem]) -> dict[str, list[DryRunItem]]:
    """Group items by label, preserving insertion order."""
    groups: dict[str, list[DryRunItem]] = defaultdict(list)
    for item in items:
        groups[item.label].append(item)
    return groups


def count_by_status(items: list[DryRunItem]) -> dict[DryRunStatus, int]:
    """Return counts of items grouped by status."""
    by_status: dict[DryRunStatus, int] = {}
    for item in items:
        by_status[item.status] = by_status.get(item.status, 0) + 1
    return by_status
