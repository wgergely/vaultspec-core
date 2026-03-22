"""Tests for dry-run data models and helpers."""

import pytest

from vaultspec_core.core.dry_run import (
    STATUS_STYLE,
    DryRunItem,
    DryRunStatus,
    count_by_status,
    group_by_label,
)

pytestmark = [pytest.mark.unit]


class TestDryRunStatus:
    def test_enum_values(self):
        assert DryRunStatus.NEW.value == "new"
        assert DryRunStatus.EXISTS.value == "exists"
        assert DryRunStatus.UPDATE.value == "update"
        assert DryRunStatus.OVERRIDE.value == "override"
        assert DryRunStatus.DELETE.value == "delete"

    def test_all_statuses_have_styles(self):
        for status in DryRunStatus:
            assert status in STATUS_STYLE


class TestDryRunItem:
    def test_creation(self):
        item = DryRunItem(".vaultspec/", DryRunStatus.NEW)
        assert item.path == ".vaultspec/"
        assert item.status == DryRunStatus.NEW

    def test_default_label(self):
        item = DryRunItem("x", DryRunStatus.EXISTS)
        assert item.label == ""

    def test_custom_label(self):
        item = DryRunItem("x", DryRunStatus.NEW, label="rules")
        assert item.label == "rules"


class TestGroupByLabel:
    def test_groups_items(self):
        items = [
            DryRunItem("a", DryRunStatus.NEW, label="rules"),
            DryRunItem("b", DryRunStatus.EXISTS, label="config"),
            DryRunItem("c", DryRunStatus.NEW, label="rules"),
        ]
        groups = group_by_label(items)
        assert len(groups["rules"]) == 2
        assert len(groups["config"]) == 1

    def test_empty_list(self):
        assert group_by_label([]) == {}


class TestCountByStatus:
    def test_counts(self):
        items = [
            DryRunItem("a", DryRunStatus.NEW),
            DryRunItem("b", DryRunStatus.NEW),
            DryRunItem("c", DryRunStatus.EXISTS),
            DryRunItem("d", DryRunStatus.DELETE),
        ]
        counts = count_by_status(items)
        assert counts[DryRunStatus.NEW] == 2
        assert counts[DryRunStatus.EXISTS] == 1
        assert counts[DryRunStatus.DELETE] == 1

    def test_empty_list(self):
        assert count_by_status([]) == {}
