from __future__ import annotations

import pathlib
import sys

import pytest

# Add the library to the path once at the top-level conftest.
# This avoids doing it in every single test file.
# Ideally, the user would run pytest with PYTHONPATH=.rules/lib/src
LIB_SRC = pathlib.Path(__file__).parent.parent / ".rules" / "lib" / "src"
if str(LIB_SRC) not in sys.path:
    sys.path.insert(0, str(LIB_SRC))


@pytest.fixture
def mock_root_dir(tmp_path):
    """A temporary directory acting as the project root."""
    (tmp_path / ".rules" / "agents").mkdir(parents=True)
    (tmp_path / ".docs" / "adr").mkdir(parents=True)
    (tmp_path / "test.txt").write_text(
        "Hello from test workspace\nLine 2\nLine 3", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def test_agent_md():
    return """---
tier: LOW
model: gemini-2.5-flash
description: "A test agent"
---

# Agent Persona
You are a helpful French Baker.
"""
