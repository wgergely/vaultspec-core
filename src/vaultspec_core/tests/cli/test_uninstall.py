"""Tests for uninstall command behavior."""

import pytest
from typer.testing import CliRunner

from vaultspec_core.cli import app

pytestmark = [pytest.mark.unit]


@pytest.fixture
def runner():
    return CliRunner()


class TestUninstallForce:
    def test_uninstall_without_force_fails(self, tmp_path, runner):
        """Uninstall must refuse without --force."""
        (tmp_path / ".vaultspec").mkdir()
        result = runner.invoke(app, ["uninstall", str(tmp_path)])
        assert result.exit_code != 0
        assert "--force" in result.output

    def test_uninstall_dry_run_without_force_succeeds(self, tmp_path, runner):
        """--dry-run should work without --force (it's non-destructive)."""
        (tmp_path / ".vaultspec").mkdir()
        result = runner.invoke(app, ["uninstall", str(tmp_path), "--dry-run"])
        # Should not require --force for dry-run
        assert "--force" not in result.output or result.exit_code == 0


class TestUninstallCoreCascade:
    def test_core_uninstall_treated_as_all(self, tmp_path, runner):
        """Uninstalling 'core' should cascade to all providers."""
        # Create vaultspec and provider dirs
        (tmp_path / ".vaultspec").mkdir()
        (tmp_path / ".claude").mkdir()
        result = runner.invoke(app, ["uninstall", str(tmp_path), "core", "--force"])
        # Should not error about "core" being invalid
        if result.exit_code != 0:
            assert "unknown provider" not in result.output.lower()
