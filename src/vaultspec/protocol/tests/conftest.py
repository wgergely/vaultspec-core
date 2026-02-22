"""Protocol unit test fixtures."""

import pytest

from ..providers import GeminiModels


@pytest.fixture
def test_root_dir(tmp_path):
    """A temporary directory acting as the project root."""
    (tmp_path / ".vaultspec" / "rules" / "agents").mkdir(parents=True)
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
