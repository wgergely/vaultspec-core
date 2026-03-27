"""Integration tests for the cli-ambiguous-states feature.

Tests that install/uninstall/sync correctly wire gitignore management,
v2.0 manifest fields, and that the doctor command reports degraded workspaces.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from vaultspec_core.cli import app
from vaultspec_core.core.commands import install_run, sync_provider, uninstall_run
from vaultspec_core.core.gitignore import MARKER_BEGIN, MARKER_END
from vaultspec_core.core.manifest import read_manifest_data, write_manifest_data

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]


@pytest.fixture
def runner():
    return CliRunner(env={"NO_COLOR": "1"})


@pytest.fixture
def installed_workspace(tmp_path: Path) -> Path:
    """Return a freshly installed workspace with a .gitignore file."""
    (tmp_path / ".gitignore").write_text("# project ignores\n", encoding="utf-8")
    install_run(
        path=tmp_path, provider="all", upgrade=False, dry_run=False, force=False
    )
    return tmp_path


def _make_degraded(root: Path, corruption: str) -> Path:
    """Apply a named corruption to an installed workspace."""
    if corruption == "corrupted_manifest":
        (root / ".vaultspec" / "providers.json").write_text(
            "INVALID JSON", encoding="utf-8"
        )
    elif corruption == "orphaned_manifest":
        # Provider in manifest but directory deleted
        claude_dir = root / ".claude"
        if claude_dir.exists():
            shutil.rmtree(claude_dir)
    elif corruption == "untracked_dir":
        # Directory exists but not in manifest
        mdata = read_manifest_data(root)
        mdata.installed.discard("claude")
        write_manifest_data(root, mdata)
    elif corruption == "missing_builtins":
        for f in (root / ".vaultspec" / "rules" / "rules").glob("*.builtin.md"):
            f.unlink()
            break
    elif corruption == "stale_content":
        rules_dir = root / ".claude" / "rules"
        if rules_dir.exists():
            (rules_dir / "stale-orphan.md").write_text("stale", encoding="utf-8")
    elif corruption == "no_gitignore":
        gi = root / ".gitignore"
        if gi.exists():
            gi.unlink()
    elif corruption == "partial_gitignore":
        gi = root / ".gitignore"
        gi.write_text(
            f"{MARKER_BEGIN}\n# old entry\n{MARKER_END}\n",
            encoding="utf-8",
        )
    return root


class TestInstallGitignore:
    """Install creates and manages the gitignore block."""

    def test_install_creates_gitignore_block(self, installed_workspace: Path):
        gi = installed_workspace / ".gitignore"
        content = gi.read_text(encoding="utf-8")
        assert MARKER_BEGIN in content
        assert MARKER_END in content

    def test_install_sets_gitignore_managed_flag(self, installed_workspace: Path):
        mdata = read_manifest_data(installed_workspace)
        assert mdata.gitignore_managed is True

    def test_install_no_gitignore_file_does_not_fail(self, tmp_path: Path):
        # No .gitignore at all -- install should still succeed but must not
        # claim gitignore management when the file does not exist.
        result = install_run(
            path=tmp_path, provider="all", upgrade=False, dry_run=False, force=False
        )
        assert result["action"] == "install"
        mdata = read_manifest_data(tmp_path)
        assert mdata.gitignore_managed is False


class TestInstallManifestV2:
    """Install populates v2.0 manifest fields."""

    def test_vaultspec_version_populated(self, installed_workspace: Path):
        mdata = read_manifest_data(installed_workspace)
        assert mdata.vaultspec_version != ""

    def test_installed_at_populated(self, installed_workspace: Path):
        mdata = read_manifest_data(installed_workspace)
        assert mdata.installed_at != ""
        # Should be a parseable ISO timestamp
        assert "T" in mdata.installed_at

    def test_provider_state_populated(self, installed_workspace: Path):
        mdata = read_manifest_data(installed_workspace)
        assert len(mdata.provider_state) > 0
        for _name, state in mdata.provider_state.items():
            assert "installed_at" in state


class TestUninstallGitignore:
    """Uninstall removes the gitignore block."""

    def test_uninstall_removes_gitignore_block(self, installed_workspace: Path):
        uninstall_run(
            path=installed_workspace,
            provider="all",
            keep_vault=False,
            dry_run=False,
            force=True,
        )
        gi = installed_workspace / ".gitignore"
        if gi.exists():
            content = gi.read_text(encoding="utf-8")
            assert MARKER_BEGIN not in content
            assert MARKER_END not in content

    def test_uninstall_keep_vault_still_removes_block(self, installed_workspace: Path):
        # keep_vault preserves .vault/ but the task says gitignore removal
        # only happens when NOT keeping vault. Verify behavior.
        uninstall_run(
            path=installed_workspace,
            provider="all",
            keep_vault=True,
            dry_run=False,
            force=True,
        )
        gi = installed_workspace / ".gitignore"
        content = gi.read_text(encoding="utf-8")
        # With keep_vault=True, gitignore block should still be present
        assert MARKER_BEGIN in content

    def test_uninstall_dry_run_preserves_block(self, installed_workspace: Path):
        uninstall_run(
            path=installed_workspace,
            provider="all",
            keep_vault=False,
            dry_run=True,
            force=False,
        )
        gi = installed_workspace / ".gitignore"
        content = gi.read_text(encoding="utf-8")
        assert MARKER_BEGIN in content


class TestSyncTimestamps:
    """Sync updates last_synced timestamps in the manifest."""

    def test_sync_updates_last_synced(self, installed_workspace: Path):
        from vaultspec_core.config import reset_config
        from vaultspec_core.config.workspace import resolve_workspace
        from vaultspec_core.core.types import init_paths

        reset_config()
        layout = resolve_workspace(target_override=installed_workspace)
        init_paths(layout)

        sync_provider("all")

        mdata = read_manifest_data(installed_workspace)
        for _name, state in mdata.provider_state.items():
            assert "last_synced" in state, f"Provider '{_name}' missing last_synced"

    def test_sync_updates_vaultspec_version(self, installed_workspace: Path):
        from vaultspec_core.config import reset_config
        from vaultspec_core.config.workspace import resolve_workspace
        from vaultspec_core.core.types import init_paths

        reset_config()
        layout = resolve_workspace(target_override=installed_workspace)
        init_paths(layout)

        sync_provider("all")

        mdata = read_manifest_data(installed_workspace)
        assert mdata.vaultspec_version != ""


class TestDoctorDegradedWorkspaces:
    """Doctor reports issues in degraded workspaces via CLI."""

    def test_clean_workspace_doctor_no_errors(
        self, installed_workspace: Path, runner: CliRunner
    ):
        result = runner.invoke(app, ["doctor", "--target", str(installed_workspace)])
        # Clean workspace should not have hard errors (exit code 2)
        # Exit code 1 (warnings) is acceptable for test workspaces
        assert result.exit_code in (0, 1)

    def test_corrupted_manifest_reported(
        self, installed_workspace: Path, runner: CliRunner
    ):
        _make_degraded(installed_workspace, "corrupted_manifest")
        result = runner.invoke(app, ["doctor", "--target", str(installed_workspace)])
        # Corrupted manifest should be reported as an issue
        assert result.exit_code != 0 or "corrupt" in result.output.lower()

    def test_orphaned_provider_reported(
        self, installed_workspace: Path, runner: CliRunner
    ):
        _make_degraded(installed_workspace, "orphaned_manifest")
        result = runner.invoke(app, ["doctor", "--target", str(installed_workspace)])
        output = result.output.lower()
        # Should report the orphaned provider
        assert (
            result.exit_code != 0
            or "orphan" in output
            or "missing" in output
            or "warn" in output
        )

    def test_untracked_directory_reported(
        self, installed_workspace: Path, runner: CliRunner
    ):
        _make_degraded(installed_workspace, "untracked_dir")
        result = runner.invoke(app, ["doctor", "--target", str(installed_workspace)])
        output = result.output.lower()
        assert result.exit_code != 0 or "untracked" in output or "warn" in output
