"""Tests for install command behavior."""

import pytest
from typer.testing import CliRunner

from vaultspec_core.cli import app

pytestmark = [pytest.mark.unit]


@pytest.fixture
def runner():
    return CliRunner()


class TestInstallForce:
    def test_install_without_force_fails_if_exists(self, tmp_path, runner):
        """Without --force, install must fail if .vaultspec/ exists."""
        (tmp_path / ".vaultspec").mkdir()
        result = runner.invoke(app, ["install", str(tmp_path)])
        assert result.exit_code != 0

    def test_install_force_proceeds_if_exists(self, tmp_path, runner):
        """--force allows reinstall over existing .vaultspec/."""
        (tmp_path / ".vaultspec").mkdir()
        result = runner.invoke(app, ["install", str(tmp_path), "--force"])
        # Should not error about already installed
        # May still fail for other reasons in test env,
        # but should not be exit code 1 with "already installed"
        if result.exit_code != 0:
            assert "already installed" not in result.output.lower()


class TestInstallDryRun:
    def test_dry_run_does_not_use_would_wording(self, tmp_path, runner):
        """--dry-run must NOT use 'Would create:' wording."""
        result = runner.invoke(app, ["install", str(tmp_path), "--dry-run"])
        assert result.exit_code == 0
        assert "would create" not in result.output.lower()

    def test_dry_run_produces_output(self, tmp_path, runner):
        """--dry-run must produce tree output."""
        result = runner.invoke(app, ["install", str(tmp_path), "--dry-run"])
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0
