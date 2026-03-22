"""Shared fixtures for vault checker tests.

Resets configuration state and points checks at the bundled vaultcore
fixture tree.
"""

from pathlib import Path

import pytest

from ....config import reset_config

_REPO_ROOT = Path(__file__).resolve().parents[5]
TEST_PROJECT = _REPO_ROOT / "test-project"


@pytest.fixture(autouse=True)
def _reset_cfg():
    reset_config()
    yield
    reset_config()


@pytest.fixture
def vault_root():
    """Return the real test-project root for checker testing."""
    return TEST_PROJECT
