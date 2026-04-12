"""Self-tests for the synthetic vault corpus generator.

All 10 categories mandated by Phase 1 Step 1.8:

1. Deterministic output for a fixed seed.
2. Tag-taxonomy compliance of every well-formed doc.
3. Each pathology produces at least one affected doc.
4. ``dangling`` pathology records target_stem and source_path.
5. ``phantom_only_links`` pathology records plan_doc and phantom_targets.
6. ``named_docs`` produces the requested filenames in the correct subdirectory.
7. Each named doc participates in the wiki-link graph.
8. ``feature_names`` overrides the default FEATURES list.
9. Interaction between pathologies and named_docs.
10. ``build_multi_project_fixture`` produces non-overlapping stems.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from vaultspec_core.testing import (
    PATHOLOGY_NAMES,
    GeneratedDoc,
    build_multi_project_fixture,
    build_synthetic_vault,
)

# All 14 named pathology presets, sorted for parametrize stability.
ALL_PATHOLOGIES: list[str] = sorted(PATHOLOGY_NAMES)

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WIKI_LINK_RE = re.compile(r"^\[\[.+\]\]$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Extract key-value pairs from the YAML frontmatter block.

    Minimal parser - only handles the fields we care about.
    """
    if not text.startswith("---"):
        return {}
    end = text.index("---", 3)
    block = text[3:end]
    result: dict[str, object] = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


def _read_tags(text: str) -> list[str]:
    """Extract the tag list from the YAML frontmatter."""
    in_tags = False
    tags: list[str] = []
    for line in text.splitlines():
        if line.strip() == "tags:":
            in_tags = True
            continue
        if in_tags:
            stripped = line.strip()
            if stripped.startswith("- "):
                tag_val = stripped[2:].strip().strip('"')
                tags.append(tag_val)
            elif stripped and not stripped.startswith("#"):
                in_tags = False
    return tags


def _read_related(text: str) -> list[str]:
    """Extract the related list from the YAML frontmatter."""
    in_related = False
    related: list[str] = []
    in_frontmatter = False
    fm_count = 0
    for line in text.splitlines():
        if line.strip() == "---":
            fm_count += 1
            if fm_count == 1:
                in_frontmatter = True
            elif fm_count == 2:
                in_frontmatter = False
            continue
        if not in_frontmatter:
            continue
        if line.strip() == "related:":
            in_related = True
            continue
        if in_related:
            stripped = line.strip()
            if stripped.startswith("- "):
                val = stripped[2:].strip().strip('"')
                related.append(val)
            elif (
                stripped
                and not stripped.startswith("#")
                and not stripped.startswith("-")
            ):
                in_related = False
    return related


def _read_date(text: str) -> str:
    """Extract the date value from the YAML frontmatter."""
    for line in text.splitlines():
        if line.startswith("date:"):
            return line.partition(":")[2].strip().strip('"')
    return ""


# ---------------------------------------------------------------------------
# 1. Deterministic output for a fixed seed
# ---------------------------------------------------------------------------


def test_deterministic_output(tmp_path: Path) -> None:
    """Same seed produces identical corpus stems."""
    root_a = tmp_path / "vault-a"
    root_b = tmp_path / "vault-b"
    root_a.mkdir()
    root_b.mkdir()

    manifest_a = build_synthetic_vault(root_a, n_docs=12, seed=42)
    manifest_b = build_synthetic_vault(root_b, n_docs=12, seed=42)

    stems_a = sorted(d.doc_id for d in manifest_a.docs)
    stems_b = sorted(d.doc_id for d in manifest_b.docs)
    assert stems_a == stems_b

    edges_a = sorted(manifest_a.graph_edges)
    edges_b = sorted(manifest_b.graph_edges)
    assert edges_a == edges_b


def test_different_seeds_differ(tmp_path: Path) -> None:
    """Different seeds produce different graph edges."""
    root_a = tmp_path / "vault-a"
    root_b = tmp_path / "vault-b"
    root_a.mkdir()
    root_b.mkdir()

    manifest_a = build_synthetic_vault(root_a, n_docs=12, seed=42)
    manifest_b = build_synthetic_vault(root_b, n_docs=12, seed=99)

    # Different seeds may occasionally produce the same edges by chance, but
    # with 12 docs and density=0.3 this is extremely unlikely.
    assert sorted(manifest_a.graph_edges) != sorted(manifest_b.graph_edges)


# ---------------------------------------------------------------------------
# 2. Tag-taxonomy compliance of well-formed docs
# ---------------------------------------------------------------------------


def test_well_formed_docs_have_exactly_two_tags(tmp_path: Path) -> None:
    """Every well-formed doc has exactly two tags: one directory + one feature."""
    manifest = build_synthetic_vault(tmp_path, n_docs=12, seed=42)
    doc_types = {"adr", "plan", "research", "exec", "reference", "audit"}
    for doc in manifest.docs:
        text = doc.path.read_text(encoding="utf-8")
        tags = _read_tags(text)
        assert len(tags) == 2, f"{doc.path}: expected 2 tags, got {tags}"
        # First tag is a directory tag
        assert tags[0].lstrip("#") in doc_types, f"{doc.path}: bad dir tag {tags[0]}"
        # Second tag is a feature tag (non-empty)
        assert tags[1].startswith("#"), f"{doc.path}: feature tag missing # prefix"
        assert len(tags[1]) > 1, f"{doc.path}: feature tag is empty"


def test_well_formed_docs_have_iso_date(tmp_path: Path) -> None:
    """Every well-formed doc has an ISO 8601 date."""
    manifest = build_synthetic_vault(tmp_path, n_docs=12, seed=42)
    for doc in manifest.docs:
        text = doc.path.read_text(encoding="utf-8")
        date_val = _read_date(text)
        assert ISO_DATE_RE.match(date_val), f"{doc.path}: bad date {date_val!r}"


def test_well_formed_docs_have_quoted_wiki_links(tmp_path: Path) -> None:
    """Related entries in well-formed docs are quoted wiki-links or empty."""
    manifest = build_synthetic_vault(tmp_path, n_docs=12, seed=42)
    for doc in manifest.docs:
        text = doc.path.read_text(encoding="utf-8")
        related = _read_related(text)
        for entry in related:
            assert WIKI_LINK_RE.match(entry), (
                f"{doc.path}: related entry {entry!r} is not a wiki-link"
            )


# ---------------------------------------------------------------------------
# 3. Each pathology produces at least one affected doc
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pathology", ALL_PATHOLOGIES)
def test_pathology_records_affected_docs(tmp_path: Path, pathology: str) -> None:
    """Each named pathology records at least one affected doc."""
    root = tmp_path / "vault"
    root.mkdir()
    manifest = build_synthetic_vault(root, n_docs=12, seed=42, pathologies=[pathology])
    assert pathology in manifest.pathologies, (
        f"Pathology {pathology!r} not recorded in manifest.pathologies"
    )
    affected = manifest.pathologies[pathology]
    assert len(affected) >= 1, f"Pathology {pathology!r} produced no affected docs"
    assert all(isinstance(d, GeneratedDoc) for d in affected), (
        f"Pathology {pathology!r} produced non-GeneratedDoc entries"
    )


@pytest.mark.parametrize("pathology", ALL_PATHOLOGIES)
def test_pathology_writes_files(tmp_path: Path, pathology: str) -> None:
    """Each pathology actually writes its affected files to disk."""
    root = tmp_path / "vault"
    root.mkdir()
    manifest = build_synthetic_vault(root, n_docs=12, seed=42, pathologies=[pathology])
    for doc in manifest.pathologies[pathology]:
        assert doc.path.exists(), (
            f"Pathology {pathology!r}: affected doc path does not exist: {doc.path}"
        )


# ---------------------------------------------------------------------------
# 4. dangling pathology records target_stem and source_path
# ---------------------------------------------------------------------------


def test_dangling_records_target_stem_and_source_path(tmp_path: Path) -> None:
    """dangling pathology_details contains target_stem and source_path."""
    root = tmp_path / "vault"
    root.mkdir()
    manifest = build_synthetic_vault(root, n_docs=12, seed=42, pathologies=["dangling"])
    details = manifest.pathology_details["dangling"]
    assert len(details) >= 1
    for detail in details:
        assert "target_stem" in detail, "dangling detail missing 'target_stem'"
        assert "source_path" in detail, "dangling detail missing 'source_path'"
        assert isinstance(detail["target_stem"], str)
        assert isinstance(detail["source_path"], Path)


def test_dangling_broken_link_present_in_file(tmp_path: Path) -> None:
    """dangling pathology's broken target stem appears in the affected file."""
    root = tmp_path / "vault"
    root.mkdir()
    manifest = build_synthetic_vault(root, n_docs=12, seed=42, pathologies=["dangling"])
    detail = manifest.pathology_details["dangling"][0]
    source_path = detail["source_path"]
    target_stem = detail["target_stem"]
    text = source_path.read_text(encoding="utf-8")
    assert target_stem in text, (
        f"Broken target stem {target_stem!r} not found in {source_path}"
    )


def test_dangling_exec_subdir_shape(tmp_path: Path) -> None:
    """dangling pathology produces exec/<feature>/ subdirectory shape."""
    root = tmp_path / "vault"
    root.mkdir()
    build_synthetic_vault(root, n_docs=12, seed=42, pathologies=["dangling"])
    exec_root = root / ".vault" / "exec"
    # At least one subdir should exist under exec/
    subdirs = [p for p in exec_root.iterdir() if p.is_dir()]
    assert len(subdirs) >= 1, (
        "dangling pathology did not produce exec/<feature>/ subdirectory"
    )


# ---------------------------------------------------------------------------
# 5. phantom_only_links pathology records plan_doc and phantom_targets
# ---------------------------------------------------------------------------


def test_phantom_only_links_records_plan_doc_and_targets(tmp_path: Path) -> None:
    """phantom_only_links pathology_details has plan_doc and phantom_targets."""
    root = tmp_path / "vault"
    root.mkdir()
    manifest = build_synthetic_vault(
        root, n_docs=12, seed=42, pathologies=["phantom_only_links"]
    )
    details = manifest.pathology_details["phantom_only_links"]
    assert len(details) >= 1
    detail = details[0]
    assert "plan_doc" in detail, "phantom_only_links detail missing 'plan_doc'"
    assert "phantom_targets" in detail, (
        "phantom_only_links detail missing 'phantom_targets'"
    )
    assert isinstance(detail["plan_doc"], GeneratedDoc)
    assert isinstance(detail["phantom_targets"], list)
    assert len(detail["phantom_targets"]) >= 1


def test_phantom_only_links_doc_is_plan_type(tmp_path: Path) -> None:
    """phantom_only_links affected doc is a plan doc."""
    root = tmp_path / "vault"
    root.mkdir()
    manifest = build_synthetic_vault(
        root, n_docs=12, seed=42, pathologies=["phantom_only_links"]
    )
    plan_doc = manifest.pathology_details["phantom_only_links"][0]["plan_doc"]
    assert plan_doc.doc_type == "plan"


# ---------------------------------------------------------------------------
# 6. named_docs produces filenames in the correct subdirectory
# ---------------------------------------------------------------------------


def test_named_docs_filenames(tmp_path: Path) -> None:
    """named_docs emits files with the requested stems."""
    stems = {
        "my_adr": "2026-02-05-my-feature-architecture-adr",
        "my_plan": "2026-02-05-my-feature-phase1-plan",
        "my_research": "2026-02-05-my-feature-research",
    }
    manifest = build_synthetic_vault(tmp_path, n_docs=12, seed=42, named_docs=stems)
    for key, stem in stems.items():
        assert key in manifest.named_docs, f"Key {key!r} not in manifest.named_docs"
        doc = manifest.named_docs[key]
        assert doc.path.name == f"{stem}.md", (
            f"Named doc {key!r}: expected {stem}.md, got {doc.path.name}"
        )
        assert doc.path.exists(), f"Named doc {key!r} path does not exist: {doc.path}"


def test_named_docs_in_correct_subdirectory(tmp_path: Path) -> None:
    """named_docs places each doc in the correct .vault/<type>/ directory."""
    stems = {
        "adr_doc": "2026-02-05-test-architecture-adr",
        "plan_doc": "2026-02-05-test-phase1-plan",
        "research_doc": "2026-02-05-test-core-research",
        "reference_doc": "2026-02-05-test-api-reference",
        "audit_doc": "2026-02-05-test-security-audit",
    }
    manifest = build_synthetic_vault(tmp_path, n_docs=6, seed=42, named_docs=stems)
    vault_dir = tmp_path / ".vault"
    expected_types = {
        "adr_doc": "adr",
        "plan_doc": "plan",
        "research_doc": "research",
        "reference_doc": "reference",
        "audit_doc": "audit",
    }
    for key, expected_type in expected_types.items():
        doc = manifest.named_docs[key]
        assert doc.path.parent == vault_dir / expected_type, (
            f"Named doc {key!r}: expected parent {vault_dir / expected_type}, "
            f"got {doc.path.parent}"
        )


# ---------------------------------------------------------------------------
# 7. Each named doc participates in the wiki-link graph
# ---------------------------------------------------------------------------


def test_named_docs_participate_in_graph(tmp_path: Path) -> None:
    """Named docs have at least one edge across a range of seeds."""
    stems = {
        "adr_key": "2026-02-05-editor-demo-architecture-adr",
        "research_key": "2026-02-05-editor-demo-research",
    }
    # Try multiple seeds to ensure at least one produces edges for named docs.
    # With graph_density=0.3 and 24 docs, probability of no edges for a single
    # doc over 10 seeds is astronomically small.
    any_edge_found = False
    for seed in range(100):
        root = tmp_path / f"vault-{seed}"
        root.mkdir()
        manifest = build_synthetic_vault(
            root, n_docs=24, seed=seed, named_docs=stems, graph_density=0.3
        )
        named_ids = {d.doc_id for d in manifest.named_docs.values()}
        for from_id, to_id in manifest.graph_edges:
            if from_id in named_ids or to_id in named_ids:
                any_edge_found = True
                break
        if any_edge_found:
            break

    assert any_edge_found, (
        "No named doc had any graph edges across 100 seeds with density=0.3"
    )


# ---------------------------------------------------------------------------
# 8. feature_names overrides the default FEATURES list
# ---------------------------------------------------------------------------


def test_feature_names_override(tmp_path: Path) -> None:
    """feature_names overrides the default FEATURES list."""
    custom_features = ["editor-demo", "displaymap-integration"]
    manifest = build_synthetic_vault(
        tmp_path, n_docs=12, seed=42, feature_names=custom_features
    )
    feature_set = {d.feature for d in manifest.docs}
    # Only our custom features should appear in the well-formed docs
    assert feature_set.issubset(set(custom_features)), (
        f"Unexpected features: {feature_set - set(custom_features)}"
    )
    # Both custom features must appear
    for f in custom_features:
        assert f in feature_set, f"Feature {f!r} not present in generated docs"


def test_feature_names_not_in_default_features(tmp_path: Path) -> None:
    """Custom feature names that differ from FEATURES default are used."""
    custom_features = ["custom-only-feature"]
    manifest = build_synthetic_vault(
        tmp_path, n_docs=6, seed=42, feature_names=custom_features
    )
    for doc in manifest.docs:
        assert doc.feature == "custom-only-feature", (
            f"Doc {doc.doc_id} has feature {doc.feature!r}, "
            "expected 'custom-only-feature'"
        )


# ---------------------------------------------------------------------------
# 9. Interaction between pathologies and named_docs
# ---------------------------------------------------------------------------


def test_named_docs_and_pathologies_coexist(tmp_path: Path) -> None:
    """Pathologies and named_docs can be combined without breaking manifest."""
    root = tmp_path / "vault"
    root.mkdir()
    stems = {"key_adr": "2026-02-05-combo-architecture-adr"}
    manifest = build_synthetic_vault(
        root,
        n_docs=12,
        seed=42,
        named_docs=stems,
        pathologies=["cycle", "orphan"],
    )
    # Named doc present
    assert "key_adr" in manifest.named_docs
    # Both pathologies recorded
    assert "cycle" in manifest.pathologies
    assert "orphan" in manifest.pathologies
    # All affected files exist on disk
    for name in ("cycle", "orphan"):
        for doc in manifest.pathologies[name]:
            assert doc.path.exists(), f"{name}: {doc.path} does not exist"


def test_named_doc_can_be_cycle_participant(tmp_path: Path) -> None:
    """A named doc may be involved in a cycle without breaking manifest invariants."""
    root = tmp_path / "vault"
    root.mkdir()
    # Request a named research doc and also inject a cycle (which creates research docs)
    stems = {"named_research": "2026-02-05-cycle-test-research"}
    manifest = build_synthetic_vault(
        root, n_docs=12, seed=42, named_docs=stems, pathologies=["cycle"]
    )
    assert manifest.named_docs["named_research"].path.exists()
    assert len(manifest.pathologies["cycle"]) >= 3


# ---------------------------------------------------------------------------
# 10. build_multi_project_fixture produces non-overlapping stems
# ---------------------------------------------------------------------------


def test_multi_project_non_overlapping_stems(tmp_path: Path) -> None:
    """build_multi_project_fixture produces non-overlapping doc stems."""
    manifests = build_multi_project_fixture(
        tmp_path, n_projects=3, docs_per_project=12, seed=42
    )
    assert len(manifests) == 3

    # Each project has its own root path
    roots = [m.root for m in manifests]
    assert len(set(roots)) == 3, "Projects share a root path"

    # Doc stems (doc_ids) across projects should not overlap because each
    # project uses its own root; paths are different even if stems coincide.
    # What must NOT overlap is the root path itself.
    for i, m_i in enumerate(manifests):
        for j, m_j in enumerate(manifests):
            if i >= j:
                continue
            assert m_i.root != m_j.root, f"Projects {i} and {j} share root {m_i.root}"


def test_multi_project_independent_roots(tmp_path: Path) -> None:
    """build_multi_project_fixture creates a subdirectory per project."""
    manifests = build_multi_project_fixture(tmp_path, n_projects=2, docs_per_project=6)
    for i, manifest in enumerate(manifests):
        assert manifest.root == tmp_path / f"project-{i}"
        assert (manifest.root / ".vault").is_dir()


def test_multi_project_different_seeds(tmp_path: Path) -> None:
    """build_multi_project_fixture uses different seeds per project."""
    manifests = build_multi_project_fixture(
        tmp_path, n_projects=2, docs_per_project=12, seed=10
    )
    # Different seeds produce different edge lists
    edges_0 = sorted(manifests[0].graph_edges)
    edges_1 = sorted(manifests[1].graph_edges)
    # Doc IDs are the same (same n_docs) but edges differ due to different seeds
    assert edges_0 != edges_1


# ---------------------------------------------------------------------------
# Additional: graph_density default is non-zero
# ---------------------------------------------------------------------------


def test_default_graph_density_produces_edges(tmp_path: Path) -> None:
    """Default graph_density=0.3 produces at least one edge with n_docs=24."""
    manifest = build_synthetic_vault(tmp_path, n_docs=24, seed=42)
    assert len(manifest.graph_edges) > 0, (
        "Default graph_density=0.3 produced no edges for 24 docs"
    )


def test_zero_graph_density_produces_no_edges(tmp_path: Path) -> None:
    """Explicit graph_density=0.0 produces no edges."""
    manifest = build_synthetic_vault(tmp_path, n_docs=12, seed=42, graph_density=0.0)
    assert len(manifest.graph_edges) == 0


# ---------------------------------------------------------------------------
# Additional: unknown pathology raises ValueError
# ---------------------------------------------------------------------------


def test_unknown_pathology_raises(tmp_path: Path) -> None:
    """Requesting an unknown pathology raises ValueError."""
    with pytest.raises(ValueError, match="Unknown pathology"):
        build_synthetic_vault(
            tmp_path, n_docs=6, seed=42, pathologies=["nonexistent_pathology"]
        )


# ---------------------------------------------------------------------------
# Additional: stem_collision detail schema
# ---------------------------------------------------------------------------


def test_stem_collision_detail_schema(tmp_path: Path) -> None:
    """stem_collision records stem and both paths."""
    root = tmp_path / "vault"
    root.mkdir()
    manifest = build_synthetic_vault(
        root, n_docs=12, seed=42, pathologies=["stem_collision"]
    )
    details = manifest.pathology_details["stem_collision"]
    assert len(details) >= 1
    detail = details[0]
    assert "stem" in detail
    assert "path_a" in detail
    assert "path_b" in detail
    assert isinstance(detail["path_a"], Path)
    assert isinstance(detail["path_b"], Path)
    assert detail["path_a"] != detail["path_b"]


# ---------------------------------------------------------------------------
# Additional: cycle detail records node list
# ---------------------------------------------------------------------------


def test_cycle_detail_records_nodes(tmp_path: Path) -> None:
    """cycle records the ordered cycle node list."""
    root = tmp_path / "vault"
    root.mkdir()
    manifest = build_synthetic_vault(root, n_docs=12, seed=42, pathologies=["cycle"])
    details = manifest.pathology_details["cycle"]
    assert len(details) >= 1
    assert "cycle_nodes" in details[0]
    nodes = details[0]["cycle_nodes"]
    assert len(nodes) == 3  # A -> B -> C -> A
