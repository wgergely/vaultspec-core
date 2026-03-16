"""Integration tests for the unified vaultspec CLI and path resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from .conftest import run_vaultspec

pytestmark = [pytest.mark.unit]


class TestPathsEnvBridge:
    """Verify that path overrides (target) propagate correctly."""

    def test_target_override(self, test_project: Path, runner) -> None:
        """--target flag correctly overrides the workspace root."""
        # The test_project fixture already creates the directory and .vaultspec
        result = run_vaultspec(runner, "--target", str(test_project), "vault", "doctor")
        assert result.exit_code == 0
        assert "Vault Health Check" in result.output


class TestValidationEdgeCases:
    """Verify error handling for invalid path configurations."""

    def test_target_dir_must_exist(self, tmp_path: Path, runner) -> None:
        """Providing a nonexistent --target should exit with an error."""
        nonexistent = tmp_path / "ghost"
        result = run_vaultspec(runner, "--target", str(nonexistent), "vault", "doctor")
        assert result.exit_code == 1
        assert "does not exist" in result.output
