"""Metrics module unit test fixtures."""

import sys
from pathlib import Path

import pytest

_LIB_SRC = Path(__file__).resolve().parent.parent.parent
if str(_LIB_SRC) not in sys.path:
    sys.path.insert(0, str(_LIB_SRC))

from core.config import reset_config  # noqa: E402

TEST_PROJECT = _LIB_SRC.parent.parent.parent / "test-project"


@pytest.fixture(autouse=True)
def _reset_cfg():
    reset_config()
    yield
    reset_config()


@pytest.fixture
def vault_root():
    """Return the real test-project root for metrics testing."""
    return TEST_PROJECT
