"""Sync command: on-disk condition tests via WorkspaceFactory."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

pytestmark = [pytest.mark.integration]


class TestCleanSync:
    """Sync against a cleanly installed workspace."""

    def test_sync_on_clean_workspace_exits_zero(self, factory) -> None:
        factory.install()
        result = factory.run("sync")
        assert result.exit_code == 0, result.output

    def test_sync_produces_rule_files(self, factory: WorkspaceFactory) -> None:
        factory.install()
        factory.run("sync")
        # Only claude/gemini/antigravity receive rules; codex does not.
        for provider in ("claude", "gemini", "antigravity"):
            assert factory.provider_has_rules(provider), (
                f"Expected synced rules for {provider}"
            )


class TestCorruptedManifest:
    """Sync behaviour when providers.json is unparseable."""

    def test_sync_force_repairs_corrupted_manifest(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install().corrupt_manifest()
        assert not factory.manifest_is_valid_json()

        result = factory.run("sync", "--force")
        assert result.exit_code == 0, result.output
        assert factory.manifest_is_valid_json()

        # Providers should still be detected after repair
        manifest = factory.read_manifest()
        assert len(manifest.installed) > 0

    def test_sync_no_force_on_corrupted_shows_warning(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install().corrupt_manifest()
        result = factory.run("sync")

        # Either a non-zero exit or a warning/error in output
        has_signal = (
            result.exit_code != 0
            or "warning" in result.output.lower()
            or "error" in result.output.lower()
            or "corrupt" in result.output.lower()
            or "repair" in result.output.lower()
        )
        assert has_signal, (
            f"Expected warning or non-zero exit on corrupted manifest, "
            f"got exit_code={result.exit_code}, output:\n{result.output}"
        )


class TestOrphanedProvider:
    """Provider is in manifest but its directory was deleted."""

    def test_sync_rescaffolds_orphaned_provider(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install().delete_provider_dir("claude")
        assert not factory.provider_dir_exists("claude")

        result = factory.run("sync")
        assert result.exit_code == 0, result.output
        assert factory.provider_dir_exists("claude")


class TestUntrackedDirectory:
    """Provider directory exists on disk but is absent from the manifest."""

    def test_sync_warns_about_untracked_dir(self, factory: WorkspaceFactory) -> None:
        factory.install().remove_provider_from_manifest("claude")
        factory.run("sync")

        # Without --force the provider should NOT be adopted into the manifest
        manifest = factory.read_manifest()
        assert "claude" not in manifest.installed

    def test_sync_force_adopts_untracked_dir(self, factory: WorkspaceFactory) -> None:
        factory.install().remove_provider_from_manifest("claude")
        result = factory.run("sync", "--force")
        assert result.exit_code == 0, result.output

        manifest = factory.read_manifest()
        assert "claude" in manifest.installed


class TestStaleContent:
    """Extra file in destination that has no corresponding source."""

    def test_sync_warns_about_stale_file(self, factory: WorkspaceFactory) -> None:
        factory.install().add_stale_rule("claude")
        stale_path = factory.path / ".claude" / "rules" / "stale-orphan.md"
        assert stale_path.exists()

        factory.run("sync")
        # Without --force, the stale file must be preserved (warning only)
        assert stale_path.exists()

    def test_sync_force_prunes_stale_file(self, factory: WorkspaceFactory) -> None:
        factory.install().add_stale_rule("claude")
        stale_path = factory.path / ".claude" / "rules" / "stale-orphan.md"
        assert stale_path.exists()

        result = factory.run("sync", "--force")
        assert result.exit_code == 0, result.output
        assert not stale_path.exists()


class TestOutdatedRules:
    """Synced rule files that contain stale content from an older version."""

    def test_sync_overwrites_outdated_rules(self, factory: WorkspaceFactory) -> None:
        factory.install().outdated_vaultspec_rules("claude")
        rules_dir = factory.path / ".claude" / "rules"
        # Find the overwritten file
        outdated = [
            f
            for f in rules_dir.glob("*.md")
            if "OLD CONTENT" in f.read_text(encoding="utf-8")
        ]
        assert outdated, "Expected at least one outdated rule file"

        factory.run("sync")
        for f in outdated:
            content = f.read_text(encoding="utf-8")
            assert "OLD CONTENT" not in content, (
                f"{f.name} still contains outdated content after sync"
            )


class TestUserContentPreservation:
    """User-authored files must survive a sync."""

    def test_sync_preserves_user_content_in_provider_dir(
        self, factory: WorkspaceFactory
    ) -> None:
        factory.install().add_user_content("claude")
        user_notes = factory.path / ".claude" / "my-notes.txt"
        user_rule = factory.path / ".claude" / "rules" / "my-custom-rule.md"
        assert user_notes.exists()
        assert user_rule.exists()

        result = factory.run("sync")
        assert result.exit_code == 0, result.output
        assert user_notes.exists(), "User notes file was deleted by sync"
        assert user_rule.exists(), "User custom rule was deleted by sync"
        assert "User's personal notes" in user_notes.read_text(encoding="utf-8")


class TestGitignore:
    """Gitignore managed-block conditions."""

    def test_sync_repairs_corrupted_gitignore(self, factory: WorkspaceFactory) -> None:
        factory.install().corrupt_gitignore_block()
        # The block is corrupted (missing end marker)
        result = factory.run("sync")
        assert result.exit_code == 0, result.output
        assert factory.gitignore_has_block()

    def test_sync_respects_gitignore_opt_out(self, factory: WorkspaceFactory) -> None:
        # Opt-out requires both removing the block AND clearing the manifest flag.
        # Just removing the block from the file is not sufficient because sync
        # checks gitignore_managed in the manifest before deciding to ensure it.
        from vaultspec_core.core.manifest import read_manifest_data, write_manifest_data

        factory.install().remove_gitignore_block()
        mdata = read_manifest_data(factory.path)
        mdata.gitignore_managed = False
        write_manifest_data(factory.path, mdata)
        assert not factory.gitignore_has_block()

        factory.run("sync")
        assert not factory.gitignore_has_block()


class TestMissingRootConfig:
    """Root config file (e.g. CLAUDE.md) deleted after install."""

    def test_sync_regenerates_deleted_config(self, factory: WorkspaceFactory) -> None:
        factory.install().delete_root_config("claude")
        config_path = factory.path / "CLAUDE.md"
        assert not config_path.exists()

        result = factory.run("sync")
        assert result.exit_code == 0, result.output
        assert config_path.exists(), "CLAUDE.md was not regenerated by sync"


class TestEmptyProviderDir:
    """Provider directory exists but is empty (no rules)."""

    def test_sync_fills_empty_provider_dir(self, factory: WorkspaceFactory) -> None:
        factory.install().empty_provider_dir("claude")
        assert not factory.provider_has_rules("claude")

        result = factory.run("sync")
        assert result.exit_code == 0, result.output
        assert factory.provider_has_rules("claude")


class TestMultipleIssues:
    """Compound corruption repaired in a single --force sync."""

    def test_sync_force_handles_multiple_corruptions(
        self, factory: WorkspaceFactory
    ) -> None:
        # Note: we do NOT combine corrupt_manifest with delete_provider_dir
        # because corrupting the manifest loses the installed-provider set,
        # making rescaffolding impossible.
        (
            factory.install()
            .corrupt_gitignore_block()
            .delete_provider_dir("gemini")
            .add_stale_rule("claude")
            .outdated_vaultspec_rules("claude")
        )

        stale_path = factory.path / ".claude" / "rules" / "stale-orphan.md"
        assert stale_path.exists()
        assert not factory.provider_dir_exists("gemini")

        result = factory.run("sync", "--force")
        assert result.exit_code == 0, result.output

        # Gemini rescaffolded
        assert factory.provider_dir_exists("gemini")
        # Stale file pruned
        assert not stale_path.exists()
        # Gitignore repaired
        assert factory.gitignore_has_block()
        # Outdated rules refreshed
        rules_dir = factory.path / ".claude" / "rules"
        for md in rules_dir.glob("*.md"):
            assert "OLD CONTENT" not in md.read_text(encoding="utf-8")
