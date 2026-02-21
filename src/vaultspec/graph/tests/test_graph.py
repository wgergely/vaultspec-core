import pytest

from vaultspec.graph import DocNode, VaultGraph
from vaultspec.vaultcore import DocType

pytestmark = [pytest.mark.api]


class TestDocNode:
    def test_defaults(self):
        from pathlib import Path

        node = DocNode(path=Path("test.md"), name="test")
        assert node.doc_type is None
        assert node.tags == set()
        assert node.out_links == set()
        assert node.in_links == set()


class TestVaultGraph:
    def test_builds_many_nodes(self, vault_root):
        graph = VaultGraph(vault_root)
        assert len(graph.nodes) > 80

    def test_node_doc_types(self, vault_root):
        graph = VaultGraph(vault_root)
        node = graph.nodes["2026-02-05-editor-demo-architecture-adr"]
        assert node.doc_type == DocType.ADR

    def test_out_links_populated(self, vault_root):
        graph = VaultGraph(vault_root)
        # This ADR has related: links to research and reference docs
        node = graph.nodes["2026-02-05-editor-demo-architecture-adr"]
        assert len(node.out_links) > 0

    def test_in_links_populated(self, vault_root):
        graph = VaultGraph(vault_root)
        # Research doc linked from the architecture ADR
        node = graph.nodes.get("2026-02-05-editor-demo-research")
        assert node is not None
        assert len(node.in_links) > 0

    def test_get_hotspots(self, vault_root):
        graph = VaultGraph(vault_root)
        hotspots = graph.get_hotspots(limit=5)
        assert isinstance(hotspots, list)
        assert len(hotspots) > 0
        assert all(isinstance(h, tuple) and len(h) == 2 for h in hotspots)

    def test_get_hotspots_filter_by_type(self, vault_root):
        graph = VaultGraph(vault_root)
        adr_only = graph.get_hotspots(doc_type=DocType.ADR)
        for name, _count in adr_only:
            assert graph.nodes[name].doc_type == DocType.ADR

    def test_get_orphaned(self, vault_root):
        graph = VaultGraph(vault_root)
        orphans = graph.get_orphaned()
        assert isinstance(orphans, list)

    def test_get_invalid_links(self, vault_root):
        graph = VaultGraph(vault_root)
        invalid = graph.get_invalid_links()
        assert isinstance(invalid, list)

    def test_get_feature_rankings(self, vault_root):
        graph = VaultGraph(vault_root)
        rankings = graph.get_feature_rankings()
        assert isinstance(rankings, list)
        feature_names = [name for name, _score in rankings]
        assert "editor-demo" in feature_names
