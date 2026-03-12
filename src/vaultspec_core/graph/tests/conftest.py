"""Shared fixtures for graph tests.

Resets configuration state and points graph queries at the bundled vaultcore
fixture tree used for relationship analysis.
"""

import pytest

from tests.constants import TEST_PROJECT

from ...config import reset_config


@pytest.fixture(autouse=True)
def _reset_cfg():
    reset_config()
    yield
    reset_config()


@pytest.fixture
def vault_root():
    """Return the real test-project root for graph testing."""
    return TEST_PROJECT
