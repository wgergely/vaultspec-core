from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = [pytest.mark.integration]


def test_cli_help():
    result = subprocess.run(
        [sys.executable, ".vaultspec/scripts/subagent.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage: subagent.py" in result.stdout


def test_cli_list_agents():
    result = subprocess.run(
        [sys.executable, ".vaultspec/scripts/subagent.py", "list"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # Output should at least be valid JSON or a list of agents
    assert "agents" in result.stdout or "[]" in result.stdout
