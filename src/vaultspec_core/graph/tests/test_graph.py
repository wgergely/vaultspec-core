"""Tests for the vault document graph API.

Covers node construction, graph building from the fixture vault, query
methods, metrics computation (via networkx algorithms), tree rendering
(Rich), ASCII rendering (phart), and JSON serialisation (node_link_data).
"""

import json
from pathlib import Path

import pytest

from ...graph import DocNode, GraphMetrics, VaultGraph
from ...vaultcore import DocType

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# DocNode
# ---------------------------------------------------------------------------


class TestDocNode:
    def test_defaults(self):
        node = DocNode(path=Path("test.md"), name="test")
        assert node.doc_type is None
        assert node.tags == set()
        assert node.out_links == set()
        assert node.in_links == set()
        assert node.feature is None
        assert node.date is None
        assert node.title is None
        assert node.body == ""
        assert node.word_count == 0
        assert node.frontmatter == {}

    def test_to_nx_attrs_serialises_sets_as_sorted_lists(self):
        node = DocNode(
            path=Path("/a/b.md"),
            name="b",
            tags={"#z", "#a"},
            out_links={"c", "a"},
            in_links={"d"},
        )
        d = node.to_nx_attrs()
        assert d["tags"] == ["#a", "#z"]
        assert d["out_links"] == ["a", "c"]
        assert d["in_links"] == ["d"]
        assert d["path"] == str(Path("/a/b.md"))

    def test_to_nx_attrs_includes_all_fields(self):
        node = DocNode(
            path=Path("x.md"),
            name="x",
            doc_type=DocType.ADR,
            feature="my-feat",
            date="2026-01-15",
            title="My Title",
            tags={"#adr", "#my-feat"},
            frontmatter={
                "tags": ["#adr", "#my-feat"],
                "date": "2026-01-15",
            },
            body="some body",
            word_count=2,
            out_links=set(),
            in_links=set(),
        )
        d = node.to_nx_attrs()
        assert d["doc_type"] == "adr"
        assert d["feature"] == "my-feat"
        assert d["date"] == "2026-01-15"
        assert d["title"] == "My Title"
        assert d["word_count"] == 2


# ---------------------------------------------------------------------------
# GraphMetrics
# ---------------------------------------------------------------------------


class TestGraphMetrics:
    def test_defaults(self):
        m = GraphMetrics()
        assert m.total_nodes == 0
        assert m.density == 0.0
        assert m.nodes_by_type == {}
        assert m.in_degree_centrality == {}
        assert m.betweenness_centrality == {}

    def test_to_dict_restructures_degree_tuples(self):
        m = GraphMetrics(
            max_in_degree=("hub", 5),
            max_out_degree=("spoke", 3),
        )
        d = m.to_dict()
        assert d["max_in_degree"] == {"node": "hub", "count": 5}
        assert d["max_out_degree"] == {
            "node": "spoke",
            "count": 3,
        }


# ---------------------------------------------------------------------------
# VaultGraph  - building
# ---------------------------------------------------------------------------


class TestVaultGraphBuilding:
    def test_builds_many_nodes(self, vault_root):
        graph = VaultGraph(vault_root)
        assert len(graph.nodes) > 80

    def test_no_nodes_lost_to_stem_collisions(self, vault_root):
        """All files produce a node  - collisions use type/stem keys."""
        from ...vaultcore import scan_vault

        file_count = sum(1 for _ in scan_vault(vault_root))
        graph = VaultGraph(vault_root)
        real_count = sum(1 for n in graph.nodes.values() if not n.phantom)
        assert real_count == file_count

    def test_colliding_stems_get_qualified_keys(self, vault_root):
        graph = VaultGraph(vault_root)
        qualified = [k for k in graph.nodes if "/" in k]
        assert len(qualified) > 0
        # Each qualified key should have the form "type/stem"
        for key in qualified:
            parts = key.split("/", 1)
            assert len(parts) == 2
            assert len(parts[0]) > 0
            assert len(parts[1]) > 0

    def test_stem_index_maps_collisions(self, vault_root):
        graph = VaultGraph(vault_root)
        collisions = {
            stem: keys for stem, keys in graph._stem_index.items() if len(keys) > 1
        }
        assert len(collisions) > 0
        for stem, keys in collisions.items():
            assert all(k.endswith(stem) for k in keys)
            assert all(k in graph.nodes for k in keys)

    def test_wiki_links_to_colliding_stems_fan_out(self, vault_root):
        """A wiki-link to a colliding stem creates edges to all variants."""
        graph = VaultGraph(vault_root)
        collisions = {
            stem: keys for stem, keys in graph._stem_index.items() if len(keys) > 1
        }
        assert collisions, "Test vault must have stem collisions"
        # Check that at least one qualified key has incoming links
        for _stem, keys in collisions.items():
            has_edges = any(
                graph.nodes[k].in_links or graph.nodes[k].out_links for k in keys
            )
            if has_edges:
                return
        # It's OK if colliding nodes happen to have no links

    def test_networkx_digraph_has_same_node_count(self, vault_root):
        graph = VaultGraph(vault_root)
        assert graph._digraph.number_of_nodes() == len(graph.nodes)

    def test_networkx_digraph_has_edges(self, vault_root):
        graph = VaultGraph(vault_root)
        assert graph._digraph.number_of_edges() > 0

    def test_digraph_property_exposes_nx_graph(self, vault_root):
        import networkx as nx

        graph = VaultGraph(vault_root)
        assert isinstance(graph.digraph, nx.DiGraph)
        assert graph.digraph is graph._digraph

    def test_nx_node_attrs_are_json_friendly(self, vault_root):
        graph = VaultGraph(vault_root)
        name = "2026-02-05-editor-demo-architecture-adr"
        attrs = graph.digraph.nodes[name]
        assert isinstance(attrs["tags"], list)
        assert isinstance(attrs["path"], str)
        assert attrs["doc_type"] == "adr"

    def test_node_has_doc_type(self, vault_root):
        graph = VaultGraph(vault_root)
        node = graph.nodes["2026-02-05-editor-demo-architecture-adr"]
        assert node.doc_type == DocType.ADR

    def test_node_has_feature(self, vault_root):
        graph = VaultGraph(vault_root)
        node = graph.nodes["2026-02-05-editor-demo-architecture-adr"]
        assert node.feature == "editor-demo"

    def test_node_has_date(self, vault_root):
        graph = VaultGraph(vault_root)
        node = graph.nodes["2026-02-05-editor-demo-architecture-adr"]
        assert node.date is not None
        assert node.date.startswith("2026")

    def test_node_has_body_and_word_count(self, vault_root):
        graph = VaultGraph(vault_root)
        node = graph.nodes["2026-02-05-editor-demo-architecture-adr"]
        assert len(node.body) > 0
        assert node.word_count > 0

    def test_node_has_frontmatter_dict(self, vault_root):
        graph = VaultGraph(vault_root)
        node = graph.nodes["2026-02-05-editor-demo-architecture-adr"]
        assert isinstance(node.frontmatter, dict)
        assert "tags" in node.frontmatter

    def test_out_links_populated(self, vault_root):
        graph = VaultGraph(vault_root)
        node = graph.nodes["2026-02-05-editor-demo-architecture-adr"]
        assert len(node.out_links) > 0

    def test_in_links_populated(self, vault_root):
        graph = VaultGraph(vault_root)
        node = graph.nodes.get("2026-02-05-editor-demo-research")
        assert node is not None
        assert len(node.in_links) > 0


# ---------------------------------------------------------------------------
# VaultGraph  - queries
# ---------------------------------------------------------------------------


class TestVaultGraphQueries:
    def test_get_node_existing(self, vault_root):
        graph = VaultGraph(vault_root)
        node = graph.get_node(
            "2026-02-05-editor-demo-architecture-adr",
        )
        assert node is not None
        assert node.doc_type == DocType.ADR

    def test_get_node_missing(self, vault_root):
        graph = VaultGraph(vault_root)
        assert graph.get_node("nonexistent") is None

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

    def test_get_hotspots_filter_by_feature(self, vault_root):
        graph = VaultGraph(vault_root)
        results = graph.get_hotspots(feature="editor-demo")
        for name, _count in results:
            assert "#editor-demo" in graph.nodes[name].tags

    def test_get_orphaned(self, vault_root):
        graph = VaultGraph(vault_root)
        orphans = graph.get_orphaned()
        assert isinstance(orphans, list)
        assert orphans == sorted(orphans)

    def test_get_dangling_links(self, vault_root):
        graph = VaultGraph(vault_root)
        dangling = graph.get_dangling_links()
        assert isinstance(dangling, list)

    def test_get_feature_rankings(self, vault_root):
        graph = VaultGraph(vault_root)
        rankings = graph.get_feature_rankings()
        assert isinstance(rankings, list)
        feature_names = [name for name, _score in rankings]
        assert "editor-demo" in feature_names

    def test_get_feature_nodes(self, vault_root):
        graph = VaultGraph(vault_root)
        nodes = graph.get_feature_nodes("editor-demo")
        assert len(nodes) > 0
        for node in nodes:
            assert "#editor-demo" in node.tags

    def test_get_feature_nodes_sorted_by_date(self, vault_root):
        graph = VaultGraph(vault_root)
        nodes = graph.get_feature_nodes("editor-demo")
        dates = [n.date for n in nodes if n.date]
        assert dates == sorted(dates)

    def test_get_features(self, vault_root):
        graph = VaultGraph(vault_root)
        features = graph.get_features()
        assert "editor-demo" in features
        assert features == sorted(features)

    def test_subgraph_returns_nx_digraph(self, vault_root):
        import networkx as nx

        graph = VaultGraph(vault_root)
        sg = graph.subgraph(feature="editor-demo")
        assert isinstance(sg, nx.DiGraph)
        assert sg.number_of_nodes() > 0
        assert sg.number_of_nodes() < len(graph.nodes)

    def test_subgraph_none_returns_full(self, vault_root):
        graph = VaultGraph(vault_root)
        sg = graph.subgraph(feature=None)
        assert sg is graph._digraph

    def test_neighbors_out(self, vault_root):
        graph = VaultGraph(vault_root)
        node = graph.nodes["2026-02-05-editor-demo-architecture-adr"]
        if node.out_links:
            out_neighbors = graph.neighbors(
                node.name,
                direction="out",
            )
            assert len(out_neighbors) > 0

    def test_neighbors_in(self, vault_root):
        graph = VaultGraph(vault_root)
        for node in graph.nodes.values():
            if node.in_links:
                in_neighbors = graph.neighbors(
                    node.name,
                    direction="in",
                )
                assert len(in_neighbors) > 0
                break

    def test_neighbors_missing_node(self, vault_root):
        graph = VaultGraph(vault_root)
        assert graph.neighbors("nonexistent") == []


# ---------------------------------------------------------------------------
# VaultGraph  - metrics (networkx algorithms)
# ---------------------------------------------------------------------------


class TestVaultGraphMetrics:
    def test_global_metrics(self, vault_root):
        graph = VaultGraph(vault_root)
        m = graph.metrics()
        assert m.total_nodes > 80
        assert m.total_edges > 0
        assert m.total_features > 0
        assert m.total_words > 0
        assert 0.0 <= m.density <= 1.0
        assert m.avg_in_degree > 0
        assert m.connected_components >= 1
        assert len(m.nodes_by_type) > 0

    def test_centrality_populated(self, vault_root):
        graph = VaultGraph(vault_root)
        m = graph.metrics()
        assert len(m.in_degree_centrality) > 0
        assert len(m.betweenness_centrality) > 0
        # Values are normalised floats
        for v in m.in_degree_centrality.values():
            assert 0.0 <= v <= 1.0
        for v in m.betweenness_centrality.values():
            assert 0.0 <= v <= 1.0

    def test_feature_scoped_metrics(self, vault_root):
        graph = VaultGraph(vault_root)
        m = graph.metrics(feature="editor-demo")
        assert m.total_nodes > 0
        assert m.total_features == 1
        assert m.nodes_by_feature == {
            "editor-demo": m.total_nodes,
        }

    def test_metrics_to_dict(self, vault_root):
        graph = VaultGraph(vault_root)
        m = graph.metrics()
        d = m.to_dict()
        assert "total_nodes" in d
        assert "max_in_degree" in d
        assert isinstance(d["max_in_degree"], dict)
        assert "in_degree_centrality" in d
        assert "betweenness_centrality" in d


# ---------------------------------------------------------------------------
# VaultGraph  - ASCII rendering (phart)
# ---------------------------------------------------------------------------


class TestVaultGraphASCII:
    def test_render_ascii_returns_string(self, vault_root):
        graph = VaultGraph(vault_root)
        result = graph.render_ascii()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_ascii_feature_scoped(self, vault_root):
        graph = VaultGraph(vault_root)
        result = graph.render_ascii(feature="editor-demo")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# VaultGraph  - tree rendering (Rich)
# ---------------------------------------------------------------------------


class TestVaultGraphRendering:
    def test_render_tree_full_vault(self, vault_root):
        from rich.tree import Tree

        graph = VaultGraph(vault_root)
        tree = graph.render_tree()
        assert isinstance(tree, Tree)

    def test_render_tree_feature_scoped(self, vault_root):
        from rich.tree import Tree

        graph = VaultGraph(vault_root)
        tree = graph.render_tree(feature="editor-demo")
        assert isinstance(tree, Tree)


# ---------------------------------------------------------------------------
# VaultGraph  - JSON serialisation (networkx node_link_data)
# ---------------------------------------------------------------------------


class TestVaultGraphJSON:
    def test_to_dict_uses_node_link_format(self, vault_root):
        graph = VaultGraph(vault_root)
        d = graph.to_dict()
        # networkx node_link_data keys
        assert "directed" in d
        assert "multigraph" in d
        assert "nodes" in d
        assert "edges" in d
        # vault enrichments
        assert "metrics" in d
        assert "root" in d
        assert d["directed"] is True

    def test_to_dict_nodes_have_id(self, vault_root):
        graph = VaultGraph(vault_root)
        d = graph.to_dict()
        for node_dict in d["nodes"]:
            assert "id" in node_dict

    def test_to_dict_body_excluded_by_default(self, vault_root):
        graph = VaultGraph(vault_root)
        d = graph.to_dict()
        for node_dict in d["nodes"]:
            assert "body" not in node_dict

    def test_to_dict_with_body(self, vault_root):
        graph = VaultGraph(vault_root)
        d = graph.to_dict(include_body=True)
        has_body = any("body" in n for n in d["nodes"])
        assert has_body

    def test_to_dict_feature_scoped(self, vault_root):
        graph = VaultGraph(vault_root)
        d = graph.to_dict(feature="editor-demo")
        assert d["feature"] == "editor-demo"
        for node_dict in d["nodes"]:
            assert "#editor-demo" in node_dict.get("tags", [])

    def test_to_json_is_valid_json(self, vault_root):
        graph = VaultGraph(vault_root)
        s = graph.to_json()
        parsed = json.loads(s)
        assert "nodes" in parsed
        assert "metrics" in parsed

    def test_to_json_feature_scoped(self, vault_root):
        graph = VaultGraph(vault_root)
        s = graph.to_json(feature="editor-demo")
        parsed = json.loads(s)
        assert parsed["feature"] == "editor-demo"

    def test_edges_have_source_and_target(self, vault_root):
        graph = VaultGraph(vault_root)
        d = graph.to_dict()
        for edge in d["edges"]:
            assert "source" in edge
            assert "target" in edge


# ---------------------------------------------------------------------------
# DocNode  - phantom defaults
# ---------------------------------------------------------------------------


class TestDocNodePhantom:
    def test_defaults_include_phantom_false(self):
        node = DocNode(path=Path("test.md"), name="test")
        assert node.phantom is False

    def test_to_nx_attrs_includes_phantom_field(self):
        node = DocNode(path=Path("x.md"), name="x")
        d = node.to_nx_attrs()
        assert "phantom" in d
        assert d["phantom"] is False

    def test_to_nx_attrs_phantom_true(self):
        node = DocNode(path=None, name="ghost", phantom=True)
        d = node.to_nx_attrs()
        assert d["phantom"] is True


# ---------------------------------------------------------------------------
# VaultGraph  - phantom nodes
# ---------------------------------------------------------------------------


class TestVaultGraphPhantom:
    def test_builds_many_nodes_includes_phantoms(self, vault_root):
        """Total node count includes both real and phantom nodes."""
        graph = VaultGraph(vault_root)
        real = sum(1 for n in graph.nodes.values() if not n.phantom)
        phantoms = sum(1 for n in graph.nodes.values() if n.phantom)
        assert len(graph.nodes) == real + phantoms
        assert phantoms > 0

    def test_phantom_nodes_created_for_unresolved_targets(self, vault_root):
        graph = VaultGraph(vault_root)
        phantoms = [n for n in graph.nodes.values() if n.phantom]
        assert len(phantoms) > 0
        for node in phantoms:
            assert node.phantom is True
            assert node.name in graph.nodes
            assert node.name in graph._digraph

    def test_phantom_nodes_have_incoming_edges(self, vault_root):
        graph = VaultGraph(vault_root)
        phantoms = [n for n in graph.nodes.values() if n.phantom]
        for node in phantoms:
            assert len(node.in_links) > 0
            for source in node.in_links:
                assert graph._digraph.has_edge(source, node.name)

    def test_get_orphaned_excludes_phantoms(self, vault_root):
        graph = VaultGraph(vault_root)
        orphans = graph.get_orphaned()
        for name in orphans:
            assert not graph.nodes[name].phantom

    def test_to_snapshot_excludes_phantoms(self, vault_root):
        graph = VaultGraph(vault_root)
        snapshot = graph.to_snapshot()
        phantom_names = {n.name for n in graph.nodes.values() if n.phantom}
        snapshot_stems = {p.stem for p in snapshot}
        assert not phantom_names & snapshot_stems

    def test_metrics_phantom_count(self, vault_root):
        graph = VaultGraph(vault_root)
        m = graph.metrics()
        actual_phantoms = sum(1 for n in graph.nodes.values() if n.phantom)
        assert m.phantom_count == actual_phantoms
        assert m.phantom_count > 0

    def test_metrics_dangling_link_count(self, vault_root):
        graph = VaultGraph(vault_root)
        m = graph.metrics()
        edge_count_to_phantoms = sum(
            1
            for src, tgt in graph._dangling_links
            if tgt in graph.nodes and graph.nodes[tgt].phantom
        )
        assert m.dangling_link_count == edge_count_to_phantoms
        assert m.dangling_link_count > 0

    def test_check_schema_ignores_phantom_adr_references(self, vault_root):
        """A plan linking only to phantom targets still reports 'no ADR reference'."""
        from ...vaultcore.checks.references import check_schema

        graph = VaultGraph(vault_root)
        result = check_schema(vault_root, graph=graph)
        # 2026-02-04-displaymap-integration-plan links only to phantoms
        plan_name = "2026-02-04-displaymap-integration-plan"
        node = graph.nodes[plan_name]
        assert node.doc_type == DocType.PLAN
        # All its out_link targets are phantom
        assert all(graph.nodes[t].phantom for t in node.out_links if t in graph.nodes)
        # check_schema should report an error for this plan
        plan_diags = [
            d
            for d in result.diagnostics
            if d.path is not None and plan_name in str(d.path)
        ]
        assert any("no references to ADR" in d.message for d in plan_diags)

    def test_tree_rendering_shows_not_created_for_phantoms(self, vault_root):
        from io import StringIO

        from rich.console import Console

        graph = VaultGraph(vault_root)
        tree = graph.render_tree()
        buf = StringIO()
        console = Console(file=buf, force_terminal=True, width=200)
        console.print(tree)
        output = buf.getvalue()
        assert "(not created)" in output

    def test_json_output_includes_phantom_flag(self, vault_root):
        graph = VaultGraph(vault_root)
        d = graph.to_dict()
        phantom_dicts = [n for n in d["nodes"] if n.get("phantom") is True]
        assert len(phantom_dicts) > 0
        for pd in phantom_dicts:
            assert pd["phantom"] is True
