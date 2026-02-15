"""Protocol unit test fixtures."""

import sys
from pathlib import Path

import pytest

# Ensure lib/src is importable
_LIB_SRC = Path(__file__).resolve().parent.parent.parent
if str(_LIB_SRC) not in sys.path:
    sys.path.insert(0, str(_LIB_SRC))

# Canonical test fixture root (git-tracked seed corpus)
_PROJECT_ROOT = _LIB_SRC.parents[2]
TEST_PROJECT = _PROJECT_ROOT / "test-project"

from protocol.providers.base import GeminiModels  # noqa: E402


@pytest.fixture
def mock_root_dir(tmp_path):
    """A temporary directory acting as the project root."""
    (tmp_path / ".vaultspec" / "agents").mkdir(parents=True)
    (tmp_path / ".vault" / "adr").mkdir(parents=True)
    (tmp_path / "test.txt").write_text(
        "Hello from test workspace\nLine 2\nLine 3", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def test_agent_md():
    return f"""---
tier: LOW
model: {GeminiModels.LOW}
description: "A test agent"
---

# Agent Persona
You are a helpful French Baker.
"""
