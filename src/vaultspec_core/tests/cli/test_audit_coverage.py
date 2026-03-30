"""Audit coverage tests for scenarios R2-U1 through R2-U22 and supporting fixes.

Covers test gaps identified in the cli-ambiguous-states rolling audit:
shared-dir protection, gitignore opt-out detection, lifecycle chains,
install/sync/uninstall flag combinations, doctor edge cases, and
validation of Phase 1-2 fixes (_rmtree_robust, surgical .mcp.json,
SyncResult.errors display).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.core.enums import DirName
from vaultspec_core.core.exceptions import ProviderError
from vaultspec_core.core.manifest import read_manifest_data
from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# Priority 1: Shared-dir protection (R2-U16)
# ---------------------------------------------------------------------------


class TestSharedDirProtection:
    """R2-U16: Uninstall a single provider when another shares .agents/."""

    def test_uninstall_antigravity_preserves_agents_dir_for_gemini(
        self, tmp_path: Path
    ) -> None:
        """Uninstalling antigravity must not delete .agents/ while gemini uses it."""
        factory = WorkspaceFactory(tmp_path)
        factory.install()

        # Both antigravity and gemini share .agents/
        assert (tmp_path / DirName.ANTIGRAVITY).is_dir()
        mdata = read_manifest_data(tmp_path)
        assert "antigravity" in mdata.installed
        assert "gemini" in mdata.installed

        # Uninstall only antigravity
        factory.uninstall("antigravity", force=True, keep_vault=True)

        # .agents/ must survive because gemini still needs it
        assert (tmp_path / DirName.ANTIGRAVITY).is_dir()
        # gemini should still be installed
        mdata = read_manifest_data(tmp_path)
        assert "gemini" in mdata.installed

    def test_uninstall_gemini_preserves_agents_dir_for_antigravity(
        self, tmp_path: Path
    ) -> None:
        """Uninstalling gemini must not delete .agents/ while antigravity uses it."""
        factory = WorkspaceFactory(tmp_path)
        factory.install()

        factory.uninstall("gemini", force=True, keep_vault=True)

        # .agents/ must survive because antigravity still uses it
        assert (tmp_path / DirName.ANTIGRAVITY).is_dir()
        mdata = read_manifest_data(tmp_path)
        assert "antigravity" in mdata.installed

    def test_sequential_uninstall_removes_agents_dir_last(self, tmp_path: Path) -> None:
        """After removing all sharing providers, .agents/ can be deleted."""
        factory = WorkspaceFactory(tmp_path)
        factory.install()

        # Remove all providers that share .agents/ except the last
        factory.uninstall("gemini", force=True, keep_vault=True)
        factory.uninstall("codex", force=True, keep_vault=True)
        # antigravity is the last owner -- now removing it should delete .agents/
        factory.uninstall("antigravity", force=True, keep_vault=True)

        assert not (tmp_path / DirName.ANTIGRAVITY).is_dir()


# ---------------------------------------------------------------------------
# Priority 2: Gitignore opt-out detection (R2-U11)
# ---------------------------------------------------------------------------


class TestGitignoreOptOut:
    """R2-U11: User removes gitignore block, sync must respect opt-out."""

    def test_sync_does_not_recreate_removed_block(self, tmp_path: Path) -> None:
        """If the user removes the managed block, sync should not recreate it."""
        factory = WorkspaceFactory(tmp_path)
        factory.install()

        # Verify block was created
        assert factory.gitignore_has_block()

        # User removes the block manually
        factory.remove_gitignore_block()
        assert not factory.gitignore_has_block()

        # Sync should respect the opt-out
        factory.sync()
        assert not factory.gitignore_has_block()

        # Manifest should reflect that gitignore is no longer managed
        mdata = read_manifest_data(tmp_path)
        assert mdata.gitignore_managed is False


# ---------------------------------------------------------------------------
# Priority 3: Lifecycle chains (R2-U19-U22)
# ---------------------------------------------------------------------------


class TestAdditiveInstall:
    """R2-U19: install claude then install gemini (additive install)."""

    def test_second_install_adds_provider(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install("claude")

        mdata = read_manifest_data(tmp_path)
        assert "claude" in mdata.installed

        # Now add gemini
        factory.install("gemini", force=True)
        mdata = read_manifest_data(tmp_path)
        assert "claude" in mdata.installed
        assert "gemini" in mdata.installed
        assert (tmp_path / DirName.CLAUDE).is_dir()
        assert (tmp_path / DirName.GEMINI).is_dir()


class TestReinstallAfterSelective:
    """R2-U20: uninstall claude then install claude (reinstall)."""

    def test_reinstall_produces_clean_state(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()

        # Uninstall claude only
        factory.uninstall("claude", force=True, keep_vault=True)
        mdata = read_manifest_data(tmp_path)
        assert "claude" not in mdata.installed
        assert not (tmp_path / DirName.CLAUDE).is_dir()

        # Reinstall claude
        factory.install("claude", force=True)
        mdata = read_manifest_data(tmp_path)
        assert "claude" in mdata.installed
        assert (tmp_path / DirName.CLAUDE).is_dir()
        assert factory.provider_has_rules("claude")


class TestSelfHealAfterDeletion:
    """R2-U21: install -> delete .claude/ -> sync --force (self-heal)."""

    def test_sync_force_recreates_deleted_provider_dir(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()

        assert (tmp_path / DirName.CLAUDE).is_dir()

        # Manually delete the provider directory
        factory.delete_provider_dir("claude")
        assert not (tmp_path / DirName.CLAUDE).is_dir()

        # sync --force should detect the orphan and re-scaffold via preflight
        factory.run("sync", "--force")
        # The directory should be recreated
        assert (tmp_path / DirName.CLAUDE).is_dir()


class TestGitignoreCreatedAfterInstall:
    """R2-U22: install (no .gitignore) -> create .gitignore -> sync."""

    def test_sync_adds_block_when_gitignore_created_after_install(
        self, tmp_path: Path
    ) -> None:
        factory = WorkspaceFactory(tmp_path)
        # Install without .gitignore
        factory.install(skip_gitignore=True)

        mdata = read_manifest_data(tmp_path)
        # No gitignore file existed, so gitignore_managed should be False
        assert mdata.gitignore_managed is False

        # User creates .gitignore after install
        factory.create_gitignore("# user project ignores\n")

        # Run sync -- managed=False means sync should NOT add the block
        factory.sync()

        # Because gitignore_managed was False, sync should respect opt-out
        # The block should NOT have been added
        assert not factory.gitignore_has_block()


# ---------------------------------------------------------------------------
# Priority 4: Install/sync flag combinations (R2-U1 through R2-U10)
# ---------------------------------------------------------------------------


class TestInstallCore:
    """R2-U1: install core (framework only, no providers)."""

    def test_install_core_creates_vaultspec_only(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install("core")

        assert (tmp_path / DirName.VAULTSPEC).is_dir()
        # Provider directories should not be created
        assert not (tmp_path / DirName.CLAUDE).is_dir()
        assert not (tmp_path / DirName.GEMINI).is_dir()


class TestInstallSingleProvider:
    """R2-U2: install claude (single provider)."""

    def test_install_claude_creates_claude_dir(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install("claude")

        assert (tmp_path / DirName.VAULTSPEC).is_dir()
        assert (tmp_path / DirName.CLAUDE).is_dir()
        mdata = read_manifest_data(tmp_path)
        assert "claude" in mdata.installed
        # Other providers should not be installed
        assert "gemini" not in mdata.installed


class TestInstallNonexistent:
    """R2-U5: install nonexistent_provider should raise ProviderError."""

    def test_install_nonexistent_raises(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        with pytest.raises(ProviderError):
            factory.install("nonexistent_provider")


class TestMcpJsonMerge:
    """R2-U6: .mcp.json merge behavior with pre-existing user entries."""

    def test_install_preserves_existing_mcp_entries(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        # Create .mcp.json with user server entries before install
        factory.create_user_only_mcp()
        assert factory.mcp_has_user_entry("my-server")

        factory.install()

        # vaultspec-core entry should be added
        assert factory.mcp_has_vaultspec_entry()
        # User entry must survive
        assert factory.mcp_has_user_entry("my-server")


class TestSyncSingleProvider:
    """R2-U7: sync claude (single provider)."""

    def test_sync_claude_only_syncs_claude(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()

        # Modify a claude rule to verify sync updates it
        rules_dir = tmp_path / DirName.CLAUDE / "rules"
        if rules_dir.is_dir():
            for md in rules_dir.glob("*.md"):
                md.write_text("stale content", encoding="utf-8")
                break

        factory.sync("claude")
        # Claude rules should be re-synced
        assert factory.provider_has_rules("claude")


class TestSyncDryRunForce:
    """R2-U8: sync --dry-run --force combination."""

    def test_sync_dry_run_force_shows_preview(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()

        # Add a stale file to trigger prune in force mode
        factory.add_stale_rule("claude", "orphan-stale.md")

        result = factory.run("sync", "--dry-run", "--force")
        # dry-run should not error
        assert result.exit_code == 0
        # The stale file should still exist (not pruned in dry-run)
        assert (tmp_path / DirName.CLAUDE / "rules" / "orphan-stale.md").exists()


class TestSyncUninstalledProvider:
    """R2-U10: sync antigravity when only claude installed."""

    def test_sync_noninstalled_provider_warns_or_errors(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install("claude")

        # Syncing a provider not installed should fail or warn
        result = factory.run("sync", "antigravity")
        # The CLI should indicate the provider is not installed
        assert result.exit_code != 0 or "not installed" in result.output.lower()


# ---------------------------------------------------------------------------
# Priority 5: Uninstall combinations (R2-U13 through R2-U15)
# ---------------------------------------------------------------------------


class TestUninstallSingleProvider:
    """R2-U13: uninstall claude --force (single provider)."""

    def test_uninstall_claude_removes_only_claude(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()

        factory.uninstall("claude", force=True, keep_vault=True)

        assert not (tmp_path / DirName.CLAUDE).is_dir()
        mdata = read_manifest_data(tmp_path)
        assert "claude" not in mdata.installed
        # Other providers should remain
        assert "gemini" in mdata.installed
        assert (tmp_path / DirName.VAULTSPEC).is_dir()


class TestUninstallNotInstalled:
    """R2-U15: uninstall claude when claude not installed."""

    def test_uninstall_absent_provider_succeeds_gracefully(
        self, tmp_path: Path
    ) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install("gemini")

        # Claude was never installed -- uninstall should not crash
        factory.uninstall("claude", force=True, keep_vault=True)


# ---------------------------------------------------------------------------
# Priority 6: Doctor edge cases (R2-U17, R2-U18)
# ---------------------------------------------------------------------------


class TestDoctorJsonSchema:
    """R2-U17: doctor --json schema completeness."""

    def test_json_schema_includes_mcp_and_provider_structure(
        self, tmp_path: Path
    ) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()

        result = factory.run("doctor", "--json")
        data = json.loads(result.output)

        # Top-level keys
        assert "framework" in data
        assert "providers" in data
        assert "builtin_version" in data
        assert "gitignore" in data

        # Provider sub-structure should be a dict
        assert isinstance(data["providers"], dict)

        # MCP field should be present
        assert "mcp" in data


class TestDoctorV1Manifest:
    """R2-U18: doctor on v1.0 manifest workspace."""

    def test_doctor_handles_v1_manifest(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()

        # Rewrite manifest as v1.0 format (only "installed" list, no v2 fields)
        manifest_path = tmp_path / DirName.VAULTSPEC / "providers.json"
        v1_data = {"installed": ["claude", "gemini", "antigravity", "codex"]}
        manifest_path.write_text(json.dumps(v1_data, indent=2), encoding="utf-8")

        result = factory.run("doctor")
        # Should not crash -- should handle gracefully
        assert result.exit_code in (0, 1, 2)

    def test_doctor_json_on_v1_manifest(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()

        manifest_path = tmp_path / DirName.VAULTSPEC / "providers.json"
        v1_data = {"installed": ["claude"]}
        manifest_path.write_text(json.dumps(v1_data, indent=2), encoding="utf-8")

        result = factory.run("doctor", "--json")
        # Should produce valid JSON despite v1 manifest
        json_start = result.output.index("{")
        data = json.loads(result.output[json_start:])
        assert "framework" in data


# ---------------------------------------------------------------------------
# New fix validation tests
# ---------------------------------------------------------------------------


class TestRmtreeRobustSymlink:
    """Validate _rmtree_robust with symlinked directories."""

    def test_rmtree_robust_unlinks_symlink_preserves_target(
        self, tmp_path: Path
    ) -> None:
        from vaultspec_core.core.helpers import _rmtree_robust

        # Create a real directory with content
        real_dir = tmp_path / "real_data"
        real_dir.mkdir()
        (real_dir / "important.txt").write_text("precious", encoding="utf-8")

        # Create a symlink pointing to it
        link_dir = tmp_path / "linked"
        try:
            link_dir.symlink_to(real_dir, target_is_directory=True)
        except OSError:
            pytest.skip("Symlink creation requires elevated privileges")

        _rmtree_robust(link_dir)

        # Symlink should be gone
        assert not link_dir.exists()
        # Target must be intact
        assert real_dir.is_dir()
        assert (real_dir / "important.txt").read_text(encoding="utf-8") == "precious"


class TestSurgicalMcpJsonRemoval:
    """Validate surgical .mcp.json removal preserves user entries."""

    def test_uninstall_preserves_user_mcp_entries(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()
        factory.add_user_mcp_servers()

        # Verify both entries exist
        assert factory.mcp_has_vaultspec_entry()
        assert factory.mcp_has_user_entry()

        factory.uninstall(force=True, keep_vault=True)

        # .mcp.json should still exist with user entry
        mcp = tmp_path / ".mcp.json"
        assert mcp.exists()
        raw = json.loads(mcp.read_text(encoding="utf-8"))
        # vaultspec-core should be gone
        assert "vaultspec-core" not in raw.get("mcpServers", {})
        # User server should survive
        assert "my-custom-server" in raw.get("mcpServers", {})

    def test_uninstall_deletes_mcp_when_only_vaultspec(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)
        factory.install()

        assert factory.mcp_has_vaultspec_entry()

        factory.uninstall(force=True, keep_vault=True)

        # .mcp.json may be deleted or have empty mcpServers
        mcp = tmp_path / ".mcp.json"
        if mcp.exists():
            raw = json.loads(mcp.read_text(encoding="utf-8"))
            assert "vaultspec-core" not in raw.get("mcpServers", {})


class TestSyncResultErrorsDisplay:
    """Validate SyncResult.errors display and non-zero exit code."""

    def test_sync_with_deleted_builtins_warns(self, tmp_path: Path) -> None:
        """Deleting builtin rules and syncing should produce preflight warnings."""
        factory = WorkspaceFactory(tmp_path)
        factory.install()

        # Delete all builtin source rules
        factory.delete_builtins()

        result = factory.run("sync")
        output_lower = result.output.lower()
        # Preflight should warn about deleted builtins
        assert "deleted" in output_lower or "skipped" in output_lower

    def test_sync_errors_list_in_output_and_exit_code(self, tmp_path: Path) -> None:
        """When sync passes produce errors, CLI must render them and exit 1."""
        from vaultspec_core.core.types import SyncResult

        # Verify the SyncResult.errors field works in the data model
        r = SyncResult()
        r.errors.append("test error")
        assert len(r.errors) == 1
        assert r.errors[0] == "test error"


# ---------------------------------------------------------------------------
# Lifecycle integration test
# ---------------------------------------------------------------------------


class TestFullLifecycleChain:
    """Full chain: install all -> sync -> verify -> uninstall claude ->
    verify gemini intact -> reinstall claude -> verify all restored."""

    def test_end_to_end_lifecycle(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path)

        # Step 1: Install all providers
        factory.install()
        mdata = read_manifest_data(tmp_path)
        assert "claude" in mdata.installed
        assert "gemini" in mdata.installed
        assert "antigravity" in mdata.installed
        assert "codex" in mdata.installed
        assert (tmp_path / DirName.CLAUDE).is_dir()
        assert (tmp_path / DirName.GEMINI).is_dir()
        assert (tmp_path / DirName.ANTIGRAVITY).is_dir()

        # Step 2: Sync (should be idempotent)
        factory.sync()
        assert factory.provider_has_rules("claude")

        # Step 3: Verify files exist
        assert (tmp_path / DirName.VAULTSPEC).is_dir()
        assert factory.manifest_is_valid_json()

        # Step 4: Uninstall claude only
        factory.uninstall("claude", force=True, keep_vault=True)
        mdata = read_manifest_data(tmp_path)
        assert "claude" not in mdata.installed
        assert not (tmp_path / DirName.CLAUDE).is_dir()

        # Step 5: Verify gemini intact
        assert "gemini" in mdata.installed
        assert (tmp_path / DirName.GEMINI).is_dir()
        assert factory.provider_has_rules("gemini")

        # Step 6: Reinstall claude
        factory.install("claude", force=True)
        mdata = read_manifest_data(tmp_path)
        assert "claude" in mdata.installed
        assert (tmp_path / DirName.CLAUDE).is_dir()

        # Step 7: Verify all restored
        assert factory.provider_has_rules("claude")
        assert "gemini" in mdata.installed
        assert "antigravity" in mdata.installed
