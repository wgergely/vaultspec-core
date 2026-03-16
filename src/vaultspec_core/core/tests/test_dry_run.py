"""Tests for dry-run tree renderer."""

import pytest

from vaultspec_core.console import reset_console
from vaultspec_core.core.dry_run import DryRunItem, DryRunStatus, render_dry_run_tree

pytestmark = [pytest.mark.unit]


class TestDryRunStatus:
    def test_enum_values(self):
        assert DryRunStatus.NEW.value == "new"
        assert DryRunStatus.EXISTS.value == "exists"
        assert DryRunStatus.UPDATE.value == "update"
        assert DryRunStatus.OVERRIDE.value == "override"
        assert DryRunStatus.DELETE.value == "delete"

    def test_all_statuses_have_styles(self):
        from vaultspec_core.core.dry_run import _STATUS_STYLE

        for status in DryRunStatus:
            assert status in _STATUS_STYLE


class TestDryRunItem:
    def test_creation(self):
        item = DryRunItem(".vaultspec/", DryRunStatus.NEW)
        assert item.path == ".vaultspec/"
        assert item.status == DryRunStatus.NEW


class TestRenderDryRunTree:
    def setup_method(self):
        reset_console()

    def test_renders_new_items(self):
        """Should not crash when rendering new items."""
        items = [
            DryRunItem(".vaultspec/", DryRunStatus.NEW),
            DryRunItem(".vaultspec/rules/", DryRunStatus.NEW),
        ]
        render_dry_run_tree(items, title="Install preview")

    def test_renders_mixed_statuses(self):
        """Should handle all status types without error."""
        items = [
            DryRunItem(".vaultspec/", DryRunStatus.EXISTS),
            DryRunItem(".claude/rules/", DryRunStatus.NEW),
            DryRunItem("CLAUDE.md", DryRunStatus.UPDATE),
            DryRunItem(".gemini/", DryRunStatus.DELETE),
            DryRunItem("AGENTS.md", DryRunStatus.OVERRIDE),
        ]
        render_dry_run_tree(items, title="Preview")

    def test_renders_empty_list(self):
        """Empty items should render just the title."""
        render_dry_run_tree([], title="Empty")

    def test_custom_title(self):
        """Custom title should be accepted."""
        items = [DryRunItem("test", DryRunStatus.NEW)]
        render_dry_run_tree(items, title="Custom Title")
