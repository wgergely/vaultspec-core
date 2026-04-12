"""Tests for the dangling wiki-link checker."""

import shutil

import pytest

from ....graph import VaultGraph
from ....testing import build_synthetic_vault
from .._base import Severity
from ..dangling import check_dangling

pytestmark = [pytest.mark.unit]


@pytest.fixture
def dangling_vault(tmp_path):
    """Synthetic vault with the dangling pathology, exposing the manifest."""
    manifest = build_synthetic_vault(
        tmp_path,
        n_docs=24,
        seed=42,
        pathologies=["dangling"],
    )
    return manifest


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

    def test_fix_removes_related_entry(self, dangling_vault, tmp_path):
        """Copy the synthetic vault, run fix, verify related entry removed."""
        manifest = dangling_vault
        tmp_vault = tmp_path / "vault-copy"
        shutil.copytree(manifest.root, tmp_vault)

        graph = VaultGraph(tmp_vault)
        dangling_before = graph.get_dangling_links()
        assert len(dangling_before) > 0

        result = check_dangling(tmp_vault, graph=graph, fix=True)
        assert result.fixed_count > 0

        # Verify the specific broken target recorded in the manifest was removed.
        detail = manifest.pathology_details["dangling"][0]
        broken_stem = detail["target_stem"]
        # The source path is relative to the original root; reconstruct in copy.
        original_source = detail["source_path"]
        relative = original_source.relative_to(manifest.root)
        doc_path = tmp_vault / relative
        content = doc_path.read_text(encoding="utf-8")
        assert f"[[{broken_stem}]]" not in content
