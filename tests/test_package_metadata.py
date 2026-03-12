"""Tests for shipped package metadata and console script names."""

from __future__ import annotations

import tomllib

import pytest

from tests.constants import PROJECT_ROOT


@pytest.mark.unit
def test_project_scripts_ship_vaultspec_core_and_mcp() -> None:
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]

    assert "vaultspec-core" in scripts
    assert scripts["vaultspec-core"] == "vaultspec_core.__main__:main"
    assert "vaultspec-mcp" in scripts
    assert scripts["vaultspec-mcp"] == "vaultspec_core.mcp_server.app:run"
    assert "vaultspec" not in scripts
