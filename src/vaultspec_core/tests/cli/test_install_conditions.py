"""Install/uninstall/provider management: on-disk condition tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vaultspec_core.core.enums import DirName

if TYPE_CHECKING:
    from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fresh install
# ---------------------------------------------------------------------------


class TestFreshInstall:
    """Verify a clean install scaffolds every expected artifact."""

    def test_install_creates_all_expected_dirs(self, factory: WorkspaceFactory) -> None:
        factory.create_gitignore().run("install")

        for dirname in (
            DirName.VAULTSPEC,
            DirName.CLAUDE,
            DirName.GEMINI,
            DirName.ANTIGRAVITY,
            DirName.CODEX,
        ):
            assert (factory.root / dirname).is_dir(), f"{dirname} missing after install"

    def test_install_creates_manifest_with_all_providers(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.create_gitignore().run("install")

        manifest = factory.read_manifest()
        for provider in ("claude", "gemini", "antigravity", "codex"):
            assert provider in manifest.installed, (
                f"{provider} not in manifest.installed"
            )

    def test_install_creates_gitignore_block(self, factory: WorkspaceFactory) -> None:
        factory.create_gitignore().run("install")

        assert factory.gitignore_has_block()

    def test_install_creates_mcp_json(self, factory: WorkspaceFactory) -> None:
        factory.create_gitignore().run("install")

        assert factory.mcp_has_vaultspec_entry()


# ---------------------------------------------------------------------------
# Install with pre-existing provider dir
# ---------------------------------------------------------------------------


class TestInstallOverExisting:
    """Pre-existing provider directories must survive install."""

    def test_install_over_existing_claude_dir(self, factory: WorkspaceFactory) -> None:
        factory.preset_pre_existing_provider("claude").create_gitignore().run("install")

        # User files must survive
        user_notes = factory.root / DirName.CLAUDE / "my-notes.txt"
        assert user_notes.exists(), "user file was deleted during install"

        # Rules must be synced
        assert factory.provider_has_rules("claude")

    def test_install_over_existing_empty_provider_dir(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.create_bare_provider_dir("claude").create_gitignore().run("install")

        assert factory.provider_has_rules("claude")


# ---------------------------------------------------------------------------
# Install with pre-existing .mcp.json
# ---------------------------------------------------------------------------


class TestInstallMergesMcp:
    """User MCP entries must be preserved when install adds its own."""

    def test_install_merges_into_existing_mcp(self, factory: WorkspaceFactory) -> None:
        factory.create_user_only_mcp().create_gitignore().run("install")

        assert factory.mcp_has_vaultspec_entry(), "vaultspec entry missing"
        assert factory.mcp_has_user_entry("my-server"), "user server was dropped"


# ---------------------------------------------------------------------------
# Install --upgrade
# ---------------------------------------------------------------------------


class TestInstallManifestFields:
    """Install must populate v2 manifest metadata fields."""

    def test_install_populates_v2_manifest_fields(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install()
        manifest = factory.read_manifest()
        assert manifest.vaultspec_version, "vaultspec_version is empty after install"
        assert manifest.installed_at, "installed_at is empty after install"

    def test_install_populates_provider_state(self, factory: WorkspaceFactory) -> None:
        factory.install()
        manifest = factory.read_manifest()
        assert manifest.provider_state, "provider_state is empty after install"
        for provider, state in manifest.provider_state.items():
            assert "installed_at" in state, (
                f"provider_state[{provider}] missing installed_at"
            )


class TestVaultspecAsFile:
    """.vaultspec as a file must block install."""

    def test_vaultspec_as_file_error(self, factory: WorkspaceFactory) -> None:
        factory.vaultspec_as_file()
        result = factory.run("install")
        assert result.exit_code != 0, (
            f"Expected non-zero exit when .vaultspec is a file, got: {result.output}"
        )


class TestInstallUpgrade:
    """--upgrade must refresh versioned content without full re-scaffold."""

    def test_upgrade_on_outdated_install(self, factory: WorkspaceFactory) -> None:
        factory.install().preset_outdated_install()

        old_manifest = factory.read_manifest()
        assert old_manifest.vaultspec_version == "0.0.1"

        factory.run("install", "--upgrade")

        new_manifest = factory.read_manifest()
        assert new_manifest.vaultspec_version != "0.0.1", (
            "version was not updated after --upgrade"
        )

    def test_upgrade_force_re_opts_gitignore(self, factory: WorkspaceFactory) -> None:
        factory.install().remove_gitignore_block()
        assert not factory.gitignore_has_block()

        factory.run("install", "--upgrade", "--force")

        assert factory.gitignore_has_block(), (
            "gitignore block not restored by --upgrade --force"
        )


# ---------------------------------------------------------------------------
# Install --force over corrupted
# ---------------------------------------------------------------------------


class TestInstallForceCorrupted:
    """--force must recover a corrupted workspace."""

    def test_install_force_over_corrupted_workspace(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install().corrupt_manifest()
        assert not factory.manifest_is_valid_json()

        factory.run("install", "--force")

        assert factory.manifest_is_valid_json(), "manifest still invalid after --force"
        assert factory.is_installed


# ---------------------------------------------------------------------------
# Upgrade edge cases
# ---------------------------------------------------------------------------


class TestUpgradeEdgeCases:
    """Upgrade edge cases: re-seed builtins, dry-run, non-installed."""

    def test_upgrade_reseeds_builtins(self, factory: WorkspaceFactory) -> None:
        factory.install().delete_builtins()
        # Verify builtins were deleted
        rules_src = factory.path / ".vaultspec" / "rules" / "rules"
        assert not list(rules_src.glob("*.builtin.md")), (
            "Builtins still exist after delete_builtins"
        )

        factory.run("install", "--upgrade")
        assert list(rules_src.glob("*.builtin.md")), (
            "Builtins were not re-seeded by --upgrade"
        )

    def test_upgrade_dry_run_no_changes(self, factory: WorkspaceFactory) -> None:
        factory.install()
        manifest_before = factory.read_manifest()
        version_before = manifest_before.vaultspec_version

        factory.install(upgrade=True, dry_run=True)
        manifest_after = factory.read_manifest()
        assert manifest_after.vaultspec_version == version_before, (
            "vaultspec_version changed despite dry-run"
        )

    def test_upgrade_on_non_installed_errors(self, factory: WorkspaceFactory) -> None:
        result = factory.run("install", "--upgrade")
        assert result.exit_code != 0, (
            f"Expected non-zero exit for upgrade on non-installed workspace: "
            f"{result.output}"
        )


# ---------------------------------------------------------------------------
# Install --skip
# ---------------------------------------------------------------------------


class TestInstallSkip:
    """--skip must exclude the named component."""

    def test_skip_core_installs_provider_only(self, factory: WorkspaceFactory) -> None:
        # Pre-create .vaultspec/ so core scaffold is present
        (factory.root / ".vaultspec" / "rules" / "rules").mkdir(
            parents=True, exist_ok=True
        )
        factory.create_gitignore()
        factory.install(skip={"core"})
        # At least one provider dir should exist
        assert factory.provider_dir_exists("claude") or factory.provider_dir_exists(
            "gemini"
        ), "No provider dirs created when skipping core"

    def test_skip_provider_installs_others(self, factory: WorkspaceFactory) -> None:
        factory.create_gitignore()
        result = factory.run("install", "--skip", "claude")
        assert result.exit_code == 0, result.output
        assert factory.provider_dir_exists("gemini"), (
            "gemini not installed when skipping claude"
        )
        assert not factory.provider_dir_exists("claude"), (
            "claude was installed despite --skip claude"
        )


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------


class TestUninstall:
    """Uninstall must tear down managed artifacts cleanly."""

    def test_uninstall_removes_all_dirs(self, factory: WorkspaceFactory) -> None:
        factory.install().run("uninstall", "--force")

        assert not factory.is_installed
        for provider in ("claude", "gemini", "antigravity", "codex"):
            assert not factory.provider_dir_exists(provider), (
                f"{provider} dir still exists"
            )

    def test_uninstall_preserves_vault_by_default(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install()
        vault = factory.root / DirName.VAULT
        vault.mkdir(parents=True, exist_ok=True)
        (vault / "dummy.md").write_text("keep me", encoding="utf-8")

        factory.run("uninstall", "--force")

        assert vault.is_dir(), ".vault/ was removed without --remove-vault"

    def test_uninstall_removes_vault_with_flag(self, factory: WorkspaceFactory) -> None:
        factory.install()
        vault = factory.root / DirName.VAULT
        vault.mkdir(parents=True, exist_ok=True)
        (vault / "dummy.md").write_text("keep me", encoding="utf-8")

        factory.run("uninstall", "--remove-vault", "--force")

        assert not vault.exists(), ".vault/ survived --remove-vault"


# ---------------------------------------------------------------------------
# Uninstall preserves user MCP entries
# ---------------------------------------------------------------------------


class TestUninstallPreservesMcp:
    """Uninstall must leave user-defined MCP servers untouched."""

    def test_uninstall_preserves_user_mcp_entries(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install().add_user_mcp_servers().run("uninstall", "--force")

        assert not factory.mcp_has_vaultspec_entry(), (
            "vaultspec entry survived uninstall"
        )
        assert factory.mcp_has_user_entry("my-custom-server"), (
            "user MCP entry was deleted"
        )


# ---------------------------------------------------------------------------
# Uninstall removes gitignore block
# ---------------------------------------------------------------------------


class TestUninstallGitignore:
    """Uninstall must clean up the managed gitignore block when vault is removed."""

    def test_uninstall_preserves_gitignore_block_when_vault_kept(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install().run("uninstall", "--force")

        # Gitignore block is preserved when .vault/ is kept (default)
        assert factory.gitignore_has_block()

    def test_uninstall_removes_gitignore_block_with_remove_vault(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install().run("uninstall", "--remove-vault", "--force")

        assert not factory.gitignore_has_block()


# ---------------------------------------------------------------------------
# Single provider install/uninstall
# ---------------------------------------------------------------------------


class TestSingleProvider:
    """Operations scoped to a single provider name."""

    def test_install_single_provider(self, factory: WorkspaceFactory) -> None:
        factory.create_gitignore().run("install", "claude")

        assert factory.provider_dir_exists("claude")
        assert not factory.provider_dir_exists("gemini"), (
            "gemini installed despite single-provider request"
        )

    def test_uninstall_single_provider(self, factory: WorkspaceFactory) -> None:
        factory.install().run("uninstall", "claude", "--force")

        assert not factory.provider_dir_exists("claude"), (
            "claude dir survived uninstall"
        )
        assert factory.provider_dir_exists("gemini"), (
            "gemini was removed by single-provider uninstall"
        )


# ---------------------------------------------------------------------------
# Adding provider to existing repo
# ---------------------------------------------------------------------------


class TestAddProvider:
    """Adding a second provider to an existing installation."""

    def test_add_provider_to_existing_install(self, factory: WorkspaceFactory) -> None:
        factory.install(provider="claude").run("install", "gemini", "--force")

        manifest = factory.read_manifest()
        assert "claude" in manifest.installed
        assert "gemini" in manifest.installed


# ---------------------------------------------------------------------------
# Removing nonexistent provider
# ---------------------------------------------------------------------------


class TestRemoveNonexistent:
    """Double-uninstall must not crash."""

    def test_uninstall_nonexistent_provider(self, factory: WorkspaceFactory) -> None:
        factory.install().run("uninstall", "claude", "--force")

        # Second removal of the same provider should exit cleanly
        result = factory.run("uninstall", "claude", "--force")
        assert result.exit_code == 0, (
            f"double uninstall failed with code {result.exit_code}: {result.output}"
        )


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Uninstall single provider
# ---------------------------------------------------------------------------


class TestUninstallSingleProvider:
    """Per-provider uninstall must update manifest and preserve shared dirs."""

    def test_uninstall_single_provider_updates_manifest(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install()
        result = factory.run("uninstall", "claude", "--force")
        assert result.exit_code == 0, result.output

        manifest = factory.read_manifest()
        assert "claude" not in manifest.installed, (
            "claude still in manifest after uninstall"
        )

    def test_uninstall_preserves_shared_agents_dir(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install()
        result = factory.run("uninstall", "gemini", "--force")
        assert result.exit_code == 0, result.output

        # .agents/ is used by antigravity and must survive gemini removal
        agents_dir = factory.path / ".agents"
        assert agents_dir.is_dir(), ".agents/ was removed by gemini uninstall"

    def test_uninstall_force_removes_dir_with_user_content(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install().add_user_content("claude")
        result = factory.run("uninstall", "claude", "--force")
        assert result.exit_code == 0, result.output
        assert not factory.provider_dir_exists("claude"), (
            ".claude/ survived --force uninstall despite user content"
        )


# ---------------------------------------------------------------------------
# Uninstall --dry-run
# ---------------------------------------------------------------------------


class TestUninstallDryRun:
    """--dry-run must not actually remove anything."""

    def test_uninstall_dry_run_no_changes(self, factory: WorkspaceFactory) -> None:
        factory.install()
        result = factory.run("uninstall", "--dry-run", "--force")
        assert result.exit_code == 0, result.output

        # Everything should still exist
        assert factory.is_installed, ".vaultspec/ removed despite --dry-run"
        for provider in ("claude", "gemini", "antigravity", "codex"):
            assert factory.provider_dir_exists(provider), (
                f"{provider} dir removed despite --dry-run"
            )


# ---------------------------------------------------------------------------
# Uninstall with corrupted manifest
# ---------------------------------------------------------------------------


class TestUninstallCorruptedManifest:
    """Uninstall behaviour when manifest is unparseable."""

    def test_uninstall_corrupted_manifest_force_proceeds(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install().corrupt_manifest()
        result = factory.run("uninstall", "--force")
        assert result.exit_code == 0, result.output

        # Provider dirs should be removed
        for provider in ("claude", "gemini"):
            assert not factory.provider_dir_exists(provider), (
                f"{provider} dir survived --force uninstall with corrupted manifest"
            )

    def test_uninstall_corrupted_manifest_no_force_blocked(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install().corrupt_manifest()
        result = factory.run("uninstall")
        assert result.exit_code != 0, (
            f"Expected non-zero exit for uninstall with corrupted manifest "
            f"without --force: {result.output}"
        )


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    """Install -> uninstall -> reinstall must yield a clean workspace."""

    def test_install_uninstall_reinstall_cycle(self, factory: WorkspaceFactory) -> None:
        factory.install().run("uninstall", "--force")
        assert not factory.is_installed

        factory.run("install")
        assert factory.is_installed
        assert factory.manifest_is_valid_json()
        for provider in ("claude", "gemini", "antigravity", "codex"):
            assert factory.provider_dir_exists(provider)


# ---------------------------------------------------------------------------
# Install --skip mcp
# ---------------------------------------------------------------------------


class TestInstallSkipMcp:
    """--skip mcp must prevent MCP scaffolding."""

    def test_skip_mcp_prevents_mcp_json_creation(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.create_gitignore()
        result = factory.run("install", "--skip", "mcp")
        assert result.exit_code == 0, result.output
        assert not factory.mcp_has_vaultspec_entry(), (
            ".mcp.json vaultspec entry created despite --skip mcp"
        )

    def test_skip_mcp_still_installs_providers(self, factory: WorkspaceFactory) -> None:
        factory.create_gitignore()
        result = factory.run("install", "--skip", "mcp")
        assert result.exit_code == 0, result.output
        assert factory.provider_dir_exists("claude"), (
            "claude dir missing when --skip mcp"
        )

    def test_skip_mcp_dry_run_excludes_mcp(self, factory: WorkspaceFactory) -> None:
        factory.create_gitignore()
        result = factory.run("install", "--skip", "mcp", "--dry-run")
        assert result.exit_code == 0, result.output
        assert not factory.mcp_has_vaultspec_entry(), (
            ".mcp.json should not exist after --skip mcp --dry-run"
        )


# ---------------------------------------------------------------------------
# Sync repairs missing MCP entry
# ---------------------------------------------------------------------------


class TestSyncRepairsMcp:
    """Sync must repair a missing MCP entry."""

    def test_sync_repairs_deleted_mcp_json(self, factory: WorkspaceFactory) -> None:
        factory.install().delete_mcp_json()
        assert not (factory.root / ".mcp.json").exists()

        factory.sync()

        assert factory.mcp_has_vaultspec_entry(), (
            "sync did not repair missing .mcp.json"
        )

    def test_sync_repairs_missing_vaultspec_entry(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install().remove_mcp_vaultspec_entry()
        assert not factory.mcp_has_vaultspec_entry()

        factory.sync()

        assert factory.mcp_has_vaultspec_entry(), (
            "sync did not repair missing vaultspec-core entry"
        )

    def test_sync_preserves_user_entries_on_repair(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install().add_user_mcp_servers().remove_mcp_vaultspec_entry()

        factory.sync()

        assert factory.mcp_has_vaultspec_entry(), "vaultspec entry not repaired"
        assert factory.mcp_has_user_entry("my-custom-server"), (
            "user entry lost during MCP repair"
        )


# ---------------------------------------------------------------------------
# Upgrade re-scaffolds MCP
# ---------------------------------------------------------------------------


class TestUpgradeRepairsMcp:
    """--upgrade must repair a missing MCP entry."""

    def test_upgrade_repairs_deleted_mcp_json(self, factory: WorkspaceFactory) -> None:
        factory.install().delete_mcp_json()
        assert not (factory.root / ".mcp.json").exists()

        factory.run("install", "--upgrade")

        assert factory.mcp_has_vaultspec_entry(), (
            "--upgrade did not repair missing .mcp.json"
        )

    def test_upgrade_repairs_missing_vaultspec_entry(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install().remove_mcp_vaultspec_entry()
        assert not factory.mcp_has_vaultspec_entry()

        factory.run("install", "--upgrade")

        assert factory.mcp_has_vaultspec_entry(), (
            "--upgrade did not repair missing vaultspec-core entry"
        )
