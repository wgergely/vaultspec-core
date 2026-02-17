"""Verification module unit test fixtures."""

import pytest
from core.config import reset_config
from tests.constants import TEST_PROJECT


@pytest.fixture(autouse=True)
def _reset_cfg():
    reset_config()
    yield
    reset_config()


@pytest.fixture
def vault_root():
    """Return the real test-project root for verification testing."""
    return TEST_PROJECT
