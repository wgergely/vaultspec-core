"""Shared fixtures for graph tests.

Resets configuration state and provides a synthetic vault corpus for
relationship analysis.
"""

import pytest

from ...config import reset_config
from ...testing.synthetic import CorpusManifest, build_synthetic_vault


@pytest.fixture(autouse=True)
def _reset_cfg():
    reset_config()
    yield
    reset_config()


@pytest.fixture(scope="session")
def graph_manifest(tmp_path_factory) -> CorpusManifest:
    """Session-scoped synthetic vault for graph tests.

    Built with four feature names so literal feature assertions pass,
    two named docs so stem-based node lookups resolve, and four
    pathology presets to cover stem-collision and phantom-link tests.

    seed=9 ensures named docs have non-zero in/out edges so
    ``test_out_links_populated`` and ``test_in_links_populated`` pass.
    """
    root = tmp_path_factory.mktemp("graph_vault")
    return build_synthetic_vault(
        root,
        n_docs=120,
        seed=9,
        feature_names=[
            "editor-demo",
            "displaymap-integration",
            "alpha-engine",
            "beta-pipeline",
        ],
        named_docs={
            "editor_demo_adr": "2026-02-05-editor-demo-architecture-adr",
            "editor_demo_research": "2026-02-05-editor-demo-research",
        },
        pathologies=["cycle", "orphan", "stem_collision", "phantom_only_links"],
        graph_density=0.3,
    )


@pytest.fixture(scope="session")
def vault_root(graph_manifest: CorpusManifest):
    """Return the synthetic vault project root for graph testing."""
    return graph_manifest.root
