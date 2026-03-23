"""Tests for the dangling wiki-link checker."""

import shutil

import pytest

from ....graph import VaultGraph
from .._base import Severity
from ..dangling import check_dangling

pytestmark = [pytest.mark.unit]


class TestCheckDangling:
    def test_reports_error_for_each_dangling_link(self, vault_root):
        graph = VaultGraph(vault_root)
        result = check_dangling(vault_root, graph=graph)
        assert not result.is_clean
        # Every diagnostic must be ERROR severity
        for diag in result.diagnostics:
            assert diag.severity == Severity.ERROR
        # The count should match the number of dangling links
        dangling_links = graph.get_dangling_links()
        assert len(result.diagnostics) == len(dangling_links)

    def test_fix_removes_related_entry(self, vault_root, tmp_path):
        """Copy the test vault, run fix, verify related entry removed."""
        # Copy the test-project vault to a temporary location
        tmp_vault = tmp_path / "test-project"
        shutil.copytree(vault_root, tmp_vault)

        graph = VaultGraph(tmp_vault)
        dangling_before = graph.get_dangling_links()
        assert len(dangling_before) > 0

        result = check_dangling(tmp_vault, graph=graph, fix=True)
        assert result.fixed_count > 0

        # Verify a specific known dangling related: entry was removed.
        # The execution summary links to [[event-handling-guide]] in related:
        doc_path = (
            tmp_vault
            / ".vault"
            / "exec"
            / "2026-02-04-editor-event-handling"
            / "2026-02-04-editor-event-handling-execution-summary.md"
        )
        content = doc_path.read_text(encoding="utf-8")
        assert "[[event-handling-guide]]" not in content
