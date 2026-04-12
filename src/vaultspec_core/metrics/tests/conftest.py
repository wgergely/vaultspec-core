"""Shared fixtures for metrics tests.

Resets configuration state and provides a synthetic vault corpus for
metrics integration tests.
"""

import pytest

from ...config import reset_config
from ...testing.synthetic import build_synthetic_vault


@pytest.fixture(autouse=True)
def _reset_cfg():
    reset_config()
    yield
    reset_config()


@pytest.fixture
def vault_root(tmp_path):
    """Return a synthetic vault root sized to satisfy metrics assertions.

    Produces 96 documents across 6 doc types (16 each) and 8 distinct
    feature names so that ``total_docs > 80`` and ``total_features > 5``
    both hold comfortably.
    """
    manifest = build_synthetic_vault(
        tmp_path,
        n_docs=96,
        seed=42,
        feature_names=[
            "alpha-engine",
            "beta-pipeline",
            "gamma-index",
            "delta-store",
            "epsilon-cache",
            "zeta-router",
            "eta-scheduler",
            "theta-observer",
        ],
    )
    return manifest.root
