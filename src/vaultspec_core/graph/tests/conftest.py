"""Shared fixtures for graph tests.

Resets configuration state and points graph queries at the bundled vaultcore
fixture tree used for relationship analysis.
"""

from pathlib import Path

import pytest

from ...config import reset_config

_REPO_ROOT = Path(__file__).resolve().parents[4]
TEST_PROJECT = _REPO_ROOT / "test-project"


@pytest.fixture(autouse=True)
def _reset_cfg():
    reset_config()
    yield
    reset_config()


@pytest.fixture
def vault_root():
    """Return the real test-project root for graph testing."""
    return TEST_PROJECT
