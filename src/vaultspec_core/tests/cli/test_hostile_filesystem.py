"""Hostile filesystem tests.

Each test creates a deliberately broken workspace state and proves
the CLI handles it correctly through the full diagnose -> resolve ->
execute -> command pipeline. Tests verify FILESYSTEM STATE, not
CLI output text.
"""

from __future__ import annotations

import json
import shutil

import pytest
from typer.testing import CliRunner

from vaultspec_core.cli import app
from vaultspec_core.core.gitignore import MARKER_BEGIN, MARKER_END
from vaultspec_core.core.manifest import read_manifest_data

pytestmark = [pytest.mark.integration]


@pytest.fixture
def runner():
    return CliRunner(env={"NO_COLOR": "1"})


class TestCorruptedManifestFullRepair:
    def test_sync_force_repairs_corrupted_manifest_and_syncs(self, tmp_path, runner):
        """Install, corrupt manifest, sync --force, verify repair."""
        # 1. Clean install
        (tmp_path / ".gitignore").write_text("# user\n", encoding="utf-8")
        result = runner.invoke(app, ["-t", str(tmp_path), "install"])
        assert result.exit_code == 0

        # 2. Corrupt the manifest
        manifest = tmp_path / ".vaultspec" / "providers.json"
        manifest.write_text("{{{INVALID", encoding="utf-8")

        # 3. Run sync --force
        result = runner.invoke(app, ["-t", str(tmp_path), "sync", "--force"])

        # 4. Verify FILESYSTEM STATE:
        # - manifest is valid JSON
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        assert "installed" in raw
        # - providers detected from existing dirs
        assert "claude" in raw["installed"]
        # - sync actually produced files
        assert any((tmp_path / ".claude" / "rules").glob("*.md"))


class TestOrphanedProviderRecovery:
    def test_orphaned_provider_rescaffolded_on_sync(self, tmp_path, runner):
        """Delete provider dir (orphan in manifest), sync, verify."""
        # 1. Clean install
        (tmp_path / ".gitignore").write_text("# user\n", encoding="utf-8")
        result = runner.invoke(app, ["-t", str(tmp_path), "install"])
        assert result.exit_code == 0

        # Verify .claude exists after install
        assert (tmp_path / ".claude").is_dir()

        # 2. Delete .claude/ (orphan it - still in manifest but dir gone)
        shutil.rmtree(tmp_path / ".claude")
        assert not (tmp_path / ".claude").exists()

        # 3. Verify manifest still lists claude
        mdata = read_manifest_data(tmp_path)
        assert "claude" in mdata.installed

        # 4. Run sync
        result = runner.invoke(app, ["-t", str(tmp_path), "sync"])

        # 5. Verify FILESYSTEM STATE:
        # - .claude/ was recreated by SCAFFOLD preflight step
        assert (tmp_path / ".claude").is_dir()
        # - rules were synced into it
        assert (tmp_path / ".claude" / "rules").is_dir()


class TestUntrackedDirectoryAdoption:
    def test_pre_existing_claude_dir_adopted_on_install(self, tmp_path, runner):
        """Create .claude/ before install, verify it's adopted into manifest."""
        # 1. Create .claude/ with some user content BEFORE install
        (tmp_path / ".claude" / "rules").mkdir(parents=True)
        (tmp_path / ".claude" / "rules" / "my-custom-rule.md").write_text(
            "---\nname: custom\n---\nMy rule", encoding="utf-8"
        )

        # 2. Install
        (tmp_path / ".gitignore").write_text("# user\n", encoding="utf-8")
        result = runner.invoke(app, ["-t", str(tmp_path), "install"])
        assert result.exit_code == 0

        # 3. Verify FILESYSTEM STATE:
        # - manifest lists claude
        mdata = read_manifest_data(tmp_path)
        assert "claude" in mdata.installed
        # - user's custom rule still exists (not clobbered)
        assert (tmp_path / ".claude" / "rules" / "my-custom-rule.md").exists()


class TestGitignoreCorruptionRepair:
    def test_corrupted_gitignore_block_repaired_on_sync(self, tmp_path, runner):
        """Corrupt the gitignore block (orphaned marker), sync, verify repair."""
        # 1. Clean install
        (tmp_path / ".gitignore").write_text("# user\n", encoding="utf-8")
        result = runner.invoke(app, ["-t", str(tmp_path), "install"])
        assert result.exit_code == 0

        # 2. Corrupt the gitignore block - leave only begin marker
        gi = tmp_path / ".gitignore"
        content = gi.read_text(encoding="utf-8")
        content = content.replace(MARKER_END, "")
        gi.write_text(content, encoding="utf-8")

        # 3. Run sync
        result = runner.invoke(app, ["-t", str(tmp_path), "sync"])

        # 4. Verify FILESYSTEM STATE:
        repaired = gi.read_text(encoding="utf-8")
        assert MARKER_BEGIN in repaired
        assert MARKER_END in repaired
        assert ".vaultspec/_snapshots/" in repaired


class TestFullLifecycleRecovery:
    def test_install_corrupt_doctor_repair_doctor(self, tmp_path, runner):
        """Complete lifecycle proving the system can diagnose, repair, and verify."""
        # 1. Install
        (tmp_path / ".gitignore").write_text("# user\n", encoding="utf-8")
        result = runner.invoke(app, ["-t", str(tmp_path), "install"])
        assert result.exit_code == 0

        # 2. Doctor: should be healthy
        result = runner.invoke(
            app,
            ["spec", "doctor", "--target", str(tmp_path)],
        )
        assert result.exit_code in (0, 1)  # 0 or 1 (warnings ok)

        # 3. Corrupt manifest
        manifest = tmp_path / ".vaultspec" / "providers.json"
        manifest.write_text("BROKEN", encoding="utf-8")

        # 4. Doctor: should detect corruption
        result = runner.invoke(
            app,
            ["spec", "doctor", "--target", str(tmp_path)],
        )
        assert result.exit_code == 2  # error

        # 5. Sync --force: should repair and sync
        result = runner.invoke(app, ["-t", str(tmp_path), "sync", "--force"])
        # May exit 0 or 1 depending on warnings - but should not crash
        assert result.exit_code in (0, 1)

        # 6. Verify manifest is repaired
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        assert "installed" in raw
        assert len(raw["installed"]) > 0

        # 7. Doctor again: should be healthier
        result = runner.invoke(
            app,
            ["spec", "doctor", "--target", str(tmp_path)],
        )
        assert result.exit_code in (0, 1)


class TestMultipleCorruptions:
    def test_multiple_corruptions_all_repaired(self, tmp_path, runner):
        """Corrupt manifest + gitignore + delete dir, sync repairs all."""
        # 1. Install
        (tmp_path / ".gitignore").write_text("# user\n", encoding="utf-8")
        result = runner.invoke(app, ["-t", str(tmp_path), "install"])
        assert result.exit_code == 0

        # 2. Corrupt manifest and gitignore, delete a provider dir
        manifest = tmp_path / ".vaultspec" / "providers.json"
        manifest.write_text("CORRUPT", encoding="utf-8")
        shutil.rmtree(tmp_path / ".claude")
        # Corrupt the gitignore block by removing only the end marker
        # (orphaned begin marker triggers CORRUPTED signal and repair)
        gi = tmp_path / ".gitignore"
        content = gi.read_text(encoding="utf-8")
        content = content.replace(MARKER_END, "")
        gi.write_text(content, encoding="utf-8")

        # 3. Sync --force
        result = runner.invoke(app, ["-t", str(tmp_path), "sync", "--force"])
        assert result.exit_code in (0, 1)

        # 4. Verify ALL repairs:
        # - manifest valid
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        assert "installed" in raw
        # - .claude/ was deleted and manifest was rebuilt from disk scan,
        #   so claude should NOT be listed (dir was gone at repair time)
        assert "claude" not in raw["installed"]
        # - gitignore block restored (orphaned marker repaired)
        repaired = gi.read_text(encoding="utf-8")
        assert MARKER_BEGIN in repaired
        assert MARKER_END in repaired


class TestInstallUninstallReinstall:
    def test_full_install_uninstall_reinstall_cycle(self, tmp_path, runner):
        """Prove the full lifecycle leaves a clean workspace."""
        (tmp_path / ".gitignore").write_text("# user\n", encoding="utf-8")

        # Install
        result = runner.invoke(app, ["-t", str(tmp_path), "install"])
        assert result.exit_code == 0
        assert (tmp_path / ".vaultspec").is_dir()
        assert (tmp_path / ".claude").is_dir()

        # Uninstall
        result = runner.invoke(app, ["-t", str(tmp_path), "uninstall", "--force"])
        assert result.exit_code == 0
        assert not (tmp_path / ".vaultspec").exists()
        assert not (tmp_path / ".claude").exists()

        # Reinstall
        result = runner.invoke(app, ["-t", str(tmp_path), "install"])
        assert result.exit_code == 0
        assert (tmp_path / ".vaultspec").is_dir()
        assert (tmp_path / ".claude").is_dir()

        # Verify clean state
        mdata = read_manifest_data(tmp_path)
        assert len(mdata.installed) > 0
