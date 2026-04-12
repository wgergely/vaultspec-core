"""Shared fixtures for vault checker tests.

Resets configuration state and provides a synthetic vault root for checks.
"""

import pytest

from ....config import reset_config
from ....testing import build_synthetic_vault


@pytest.fixture(autouse=True)
def _reset_cfg():
    reset_config()
    yield
    reset_config()


@pytest.fixture
def vault_root(tmp_path):
    """Return a synthetic vault root for checker testing."""
    manifest = build_synthetic_vault(
        tmp_path,
        n_docs=24,
        seed=42,
        pathologies=["dangling"],
    )
    return manifest.root
