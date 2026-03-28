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
