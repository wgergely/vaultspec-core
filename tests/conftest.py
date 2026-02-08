"""Shared fixtures for ACP dispatcher test suite."""

from __future__ import annotations

import pathlib
import sys
import tempfile

import pytest

# Ensure the scripts directory is importable
_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


@pytest.fixture
def temp_workspace(tmp_path: pathlib.Path):
    """Creates a temporary workspace with provider agent directories and a test file."""
    # Create provider agent dirs
    (tmp_path / ".rules" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".gemini" / "agents").mkdir(parents=True)
    (tmp_path / ".agent" / "agents").mkdir(parents=True)

    # Create a test file for file I/O tests
    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello from test workspace\nLine 2\nLine 3\n", encoding="utf-8")

    return tmp_path


@pytest.fixture
def mock_root_dir(temp_workspace: pathlib.Path, monkeypatch):
    """Monkeypatches acp_dispatch.ROOT_DIR and AGENT_DIRS to use temp_workspace."""
    import acp_dispatch

    monkeypatch.setattr(acp_dispatch, "ROOT_DIR", temp_workspace)
    monkeypatch.setattr(
        acp_dispatch,
        "AGENT_DIRS",
        {
            "gemini": temp_workspace / ".gemini" / "agents",
            "claude": temp_workspace / ".claude" / "agents",
            "antigravity": temp_workspace / ".agent" / "agents",
            "rules": temp_workspace / ".rules" / "agents",
        },
    )
    return temp_workspace


@pytest.fixture
def cli_workspace(tmp_path: pathlib.Path):
    """Full isolated workspace for CLI integration tests.

    Creates all source and destination directories, populates AGENTS.md,
    and redirects CLI globals via init_paths().
    """
    import cli as cli_mod

    # Source dirs
    (tmp_path / ".rules" / "rules").mkdir(parents=True)
    (tmp_path / ".rules" / "rules-custom").mkdir(parents=True)
    (tmp_path / ".rules" / "agents").mkdir(parents=True)
    (tmp_path / ".rules" / "skills").mkdir(parents=True)

    # Destination dirs
    for tool in (".claude", ".gemini", ".agent"):
        (tmp_path / tool / "rules").mkdir(parents=True)
        (tmp_path / tool / "agents").mkdir(parents=True)
        (tmp_path / tool / "skills").mkdir(parents=True)

    # Canonical config source
    (tmp_path / ".rules" / "AGENTS.md").write_text(
        "# Test Mission\n\n- Test project.\n", encoding="utf-8"
    )

    # Redirect CLI globals to temp workspace
    cli_mod.init_paths(tmp_path)
    yield tmp_path

    # Restore default root (defensive teardown)
    _default_root = pathlib.Path(__file__).resolve().parent.parent.parent
    cli_mod.init_paths(_default_root)


@pytest.fixture(scope="session")
def test_agent_md():
    """Returns a french-croissant-style agent definition string."""
    return (
        "---\n"
        'description: "Test agent that always responds in French and loves croissants"\n'
        "tier: LOW\n"
        "---\n"
        "\n"
        "# Persona: French Baker\n"
        "\n"
        "You are a friendly French baker. Always respond in French.\n"
        "You love croissants more than anything.\n"
    )
