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
        result = runner.invoke(app, ["-t", str(tmp_path), "install"])
        assert result.exit_code != 0

    def test_install_force_proceeds_if_exists(self, tmp_path, runner):
        """--force allows reinstall over existing .vaultspec/."""
        (tmp_path / ".vaultspec").mkdir()
        result = runner.invoke(app, ["-t", str(tmp_path), "install", "--force"])
        # Should not error about already installed
        if result.exit_code != 0:
            assert "already installed" not in result.output.lower()


class TestInstallDryRun:
    def test_dry_run_does_not_use_would_wording(self, tmp_path, runner):
        """--dry-run must NOT use 'Would create:' wording."""
        result = runner.invoke(app, ["-t", str(tmp_path), "install", "--dry-run"])
        assert result.exit_code == 0
        assert "would create" not in result.output.lower()

    def test_dry_run_produces_output(self, tmp_path, runner):
        """--dry-run must produce tree output."""
        result = runner.invoke(app, ["-t", str(tmp_path), "install", "--dry-run"])
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0


class TestInstallPathSafety:
    def test_deep_nonexistent_path_rejected(self, tmp_path, runner):
        """Installing to a deeply nested non-existent path must fail."""
        target = tmp_path / "a" / "b" / "c" / "project"
        result = runner.invoke(app, ["-t", str(target), "install"])
        assert result.exit_code != 0
        assert "parent directory does not exist" in result.output.lower()
        # Must NOT have created any directories
        assert not (tmp_path / "a").exists()

    def test_single_level_nonexistent_path_creates_dir(self, tmp_path, runner):
        """Installing to a single-level non-existent path should create it."""
        target = tmp_path / "my-project"
        result = runner.invoke(app, ["-t", str(target), "install"])
        assert result.exit_code == 0
        assert target.exists()
        assert (target / ".vaultspec").exists()

    def test_dry_run_nonexistent_path_no_side_effects(self, tmp_path, runner):
        """Dry-run on a non-existent path must not create the directory."""
        target = tmp_path / "phantom"
        runner.invoke(app, ["-t", str(target), "install", "--dry-run"])
        # The key invariant: dry-run must never create the target directory
        assert not target.exists()
