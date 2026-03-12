"""Config module unit test fixtures."""

from __future__ import annotations

import pytest

from vaultspec_core.config import reset_config


@pytest.fixture
def clean_config():
    """Reset the config singleton before and after the test."""
    reset_config()
    yield
    reset_config()
