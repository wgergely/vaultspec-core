"""End-to-end tests for resolver pre-flight in CLI commands.

Exercises the full path through the CLI, verifying that diagnosis + resolution
pre-flight is transparent for clean workspaces, blocks on conflicts, and
displays warnings as expected. Assertions verify ACTUAL FILESYSTEM STATE,
not just CLI output strings.
"""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from vaultspec_core.cli import app
from vaultspec_core.core.commands import install_run
from vaultspec_core.core.manifest import read_manifest_data, write_manifest_data

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration]


@pytest.fixture
def runner():
    return CliRunner(env={"NO_COLOR": "1"})


@pytest.fixture
def installed_workspace(tmp_path: Path) -> Path:
    """Return a freshly installed workspace."""
    (tmp_path / ".gitignore").write_text("# project ignores\n", encoding="utf-8")
    install_run(
        path=tmp_path, provider="all", upgrade=False, dry_run=False, force=False
    )
    return tmp_path


# ---- (a) Clean workspace - transparent --------------------------------------


class TestCleanWorkspaceTransparent:
    """Pre-flight must be invisible for clean workspaces."""

    def test_install_clean_exits_zero(self, tmp_path: Path, runner: CliRunner):
        result = runner.invoke(app, ["-t", str(tmp_path), "install"])
        assert result.exit_code == 0

    def test_sync_after_install_exits_zero(
        self, installed_workspace: Path, runner: CliRunner
    ):
        result = runner.invoke(app, ["-t", str(installed_workspace), "sync"])
        assert result.exit_code == 0
        assert "conflict" not in result.output.lower()


# ---- (b) Corrupted manifest - install blocked / --force proceeds -------------


class TestCorruptedManifestInstall:
    """Corrupted manifest blocks install unless --force is used."""

    def _corrupt_manifest(self, root: Path) -> None:
        (root / ".vaultspec" / "providers.json").write_text(
            "INVALID JSON", encoding="utf-8"
        )

    def test_install_blocked_without_force(
        self, installed_workspace: Path, runner: CliRunner
    ):
        self._corrupt_manifest(installed_workspace)
        result = runner.invoke(app, ["-t", str(installed_workspace), "install"])
        assert result.exit_code == 1
        assert "corrupt" in result.output.lower()

    def test_install_proceeds_with_force(
        self, installed_workspace: Path, runner: CliRunner
    ):
        self._corrupt_manifest(installed_workspace)
        result = runner.invoke(
            app, ["-t", str(installed_workspace), "install", "--force"]
        )
        assert result.exit_code == 0

    def test_install_force_on_corrupted_actually_installs(
        self, tmp_path: Path, runner: CliRunner
    ):
        """Install --force on corrupted workspace repairs and installs."""
        (tmp_path / ".vaultspec").mkdir()
        (tmp_path / ".vaultspec" / "providers.json").write_text(
            "CORRUPT", encoding="utf-8"
        )
        (tmp_path / ".gitignore").write_text("# user\n", encoding="utf-8")

        result = runner.invoke(app, ["-t", str(tmp_path), "install", "--force"])
        assert result.exit_code == 0

        mdata = read_manifest_data(tmp_path)
        assert len(mdata.installed) > 0
        assert (tmp_path / ".claude" / "rules").exists()


# ---- (c) Corrupted manifest - sync shows remediation ------------------------


class TestCorruptedManifestSync:
    """Sync on corrupted manifest shows repair steps then proceeds."""

    def test_sync_corrupted_manifest_shows_repair(
        self, installed_workspace: Path, runner: CliRunner
    ):
        (installed_workspace / ".vaultspec" / "providers.json").write_text(
            "INVALID JSON", encoding="utf-8"
        )
        result = runner.invoke(app, ["-t", str(installed_workspace), "sync"])
        output = result.output.lower()
        # Sync with CORRUPTED framework always generates repair steps (per ADR)
        assert "repair" in output or "manifest" in output

    def test_sync_corrupted_manifest_actually_repairs(
        self, installed_workspace: Path, runner: CliRunner
    ):
        """Sync on corrupted manifest repairs it before syncing."""
        manifest_path = installed_workspace / ".vaultspec" / "providers.json"
        manifest_path.write_text("CORRUPT", encoding="utf-8")

        runner.invoke(app, ["-t", str(installed_workspace), "sync", "--force"])

        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "installed" in raw
        assert len(raw["installed"]) > 0


# ---- (d) Untracked directory - sync warns ------------------------------------


class TestUntrackedDirSync:
    """An untracked provider directory triggers a pre-flight warning on sync."""

    def test_sync_untracked_dir_warns(
        self, installed_workspace: Path, runner: CliRunner
    ):
        mdata = read_manifest_data(installed_workspace)
        mdata.installed.discard("claude")
        write_manifest_data(installed_workspace, mdata)

        result = runner.invoke(app, ["-t", str(installed_workspace), "sync"])
        output = result.output.lower()
        assert "untracked" in output or "!" in result.output


# ---- (e) Missing framework - sync blocked -----------------------------------


class TestMissingFrameworkSync:
    """Sync on a directory with no .vaultspec/ must fail."""

    def test_sync_no_framework_exits_nonzero(self, tmp_path: Path, runner: CliRunner):
        result = runner.invoke(app, ["-t", str(tmp_path), "sync"])
        assert result.exit_code != 0


# ---- (f) Upgrade action -----------------------------------------------------


class TestUpgradeAction:
    """Install --upgrade on an installed workspace exits cleanly."""

    def test_upgrade_installed_exits_zero(
        self, installed_workspace: Path, runner: CliRunner
    ):
        result = runner.invoke(
            app, ["-t", str(installed_workspace), "install", "--upgrade"]
        )
        assert result.exit_code == 0


# ---- (g) Dry-run with warnings ----------------------------------------------


class TestDryRunWithWarnings:
    """Dry-run should still show pre-flight warnings but not block."""

    def test_dry_run_shows_warnings_no_block(
        self, installed_workspace: Path, runner: CliRunner
    ):
        mdata = read_manifest_data(installed_workspace)
        mdata.installed.discard("claude")
        write_manifest_data(installed_workspace, mdata)

        result = runner.invoke(
            app, ["-t", str(installed_workspace), "sync", "--dry-run"]
        )
        output = result.output.lower()
        # Should show warning about untracked dir but NOT exit 1
        assert "untracked" in output or "!" in result.output
        assert result.exit_code == 0


# ---- Uninstall pre-flight ---------------------------------------------------


class TestUninstallPreflight:
    """Uninstall pre-flight blocks on corrupted manifest without --force."""

    def test_uninstall_corrupted_blocked_without_force(
        self, installed_workspace: Path, runner: CliRunner
    ):
        (installed_workspace / ".vaultspec" / "providers.json").write_text(
            "INVALID JSON", encoding="utf-8"
        )
        result = runner.invoke(app, ["-t", str(installed_workspace), "uninstall"])
        assert result.exit_code == 1
        assert "corrupt" in result.output.lower()

    def test_uninstall_corrupted_proceeds_with_force(
        self, installed_workspace: Path, runner: CliRunner
    ):
        (installed_workspace / ".vaultspec" / "providers.json").write_text(
            "INVALID JSON", encoding="utf-8"
        )
        result = runner.invoke(
            app, ["-t", str(installed_workspace), "uninstall", "--force"]
        )
        assert result.exit_code == 0


# ---- Preflight scaffolds orphaned providers ----------------------------------


class TestPreflightScaffoldsOrphaned:
    """Orphaned manifest entries trigger SCAFFOLD during preflight."""

    def test_sync_rescaffolds_deleted_provider_dir(
        self, installed_workspace: Path, runner: CliRunner
    ):
        """Delete .claude/ (making it orphaned), sync, verify .claude/ recreated."""
        shutil.rmtree(installed_workspace / ".claude")
        assert not (installed_workspace / ".claude").exists()

        runner.invoke(app, ["-t", str(installed_workspace), "sync"])

        assert (installed_workspace / ".claude").exists()
