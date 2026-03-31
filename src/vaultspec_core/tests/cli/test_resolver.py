"""Tests for the resolution engine rule matrix."""

from __future__ import annotations

import pytest

from vaultspec_core.core.diagnosis.diagnosis import (
    ProviderDiagnosis,
    WorkspaceDiagnosis,
)
from vaultspec_core.core.diagnosis.signals import (
    BuiltinVersionSignal,
    ConfigSignal,
    ContentSignal,
    FrameworkSignal,
    GitignoreSignal,
    ManifestEntrySignal,
    ProviderDirSignal,
    ResolutionAction,
)
from vaultspec_core.core.enums import Tool
from vaultspec_core.core.resolver import ResolutionPlan, resolve

pytestmark = [pytest.mark.unit]


def _make_diagnosis(
    framework: FrameworkSignal = FrameworkSignal.PRESENT,
    builtin_version: BuiltinVersionSignal = BuiltinVersionSignal.CURRENT,
    gitignore: GitignoreSignal = GitignoreSignal.COMPLETE,
    providers: dict[Tool, ProviderDiagnosis] | None = None,
) -> WorkspaceDiagnosis:
    """Build a WorkspaceDiagnosis with sensible defaults for testing."""
    if providers is None:
        providers = {}
    return WorkspaceDiagnosis(
        framework=framework,
        providers=providers,
        builtin_version=builtin_version,
        gitignore=gitignore,
    )


def _make_provider(
    tool: Tool = Tool.CLAUDE,
    dir_state: ProviderDirSignal = ProviderDirSignal.COMPLETE,
    manifest_entry: ManifestEntrySignal = ManifestEntrySignal.COHERENT,
    content: dict[str, ContentSignal] | None = None,
    config: ConfigSignal = ConfigSignal.OK,
) -> ProviderDiagnosis:
    """Build a ProviderDiagnosis with sensible defaults for testing."""
    return ProviderDiagnosis(
        tool=tool,
        dir_state=dir_state,
        manifest_entry=manifest_entry,
        content=content or {},
        config=config,
    )


# ---------------------------------------------------------------------------
# Framework rules
# ---------------------------------------------------------------------------


class TestFrameworkRules:
    """Tests for FrameworkSignal resolution rules."""

    def test_missing_install_proceeds(self):
        diag = _make_diagnosis(framework=FrameworkSignal.MISSING)
        plan = resolve(diag, "install")
        assert not plan.blocked
        assert plan.steps == []
        assert plan.warnings == []

    def test_missing_sync_errors(self):
        diag = _make_diagnosis(framework=FrameworkSignal.MISSING)
        plan = resolve(diag, "sync")
        assert plan.blocked
        assert any("not installed" in c.lower() for c in plan.conflicts)

    def test_missing_uninstall_warns(self):
        diag = _make_diagnosis(framework=FrameworkSignal.MISSING)
        plan = resolve(diag, "uninstall")
        assert not plan.blocked
        assert any("nothing to remove" in w.lower() for w in plan.warnings)

    def test_corrupted_install_no_force_conflicts(self):
        diag = _make_diagnosis(framework=FrameworkSignal.CORRUPTED)
        plan = resolve(diag, "install", force=False)
        assert plan.blocked
        assert any("corrupted" in c.lower() for c in plan.conflicts)

    def test_corrupted_install_force_repairs(self):
        diag = _make_diagnosis(framework=FrameworkSignal.CORRUPTED)
        plan = resolve(diag, "install", force=True)
        assert not plan.blocked
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.REPAIR_MANIFEST in actions

    def test_corrupted_sync_always_repairs(self):
        diag = _make_diagnosis(framework=FrameworkSignal.CORRUPTED)
        plan = resolve(diag, "sync", force=False)
        assert not plan.blocked
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.REPAIR_MANIFEST in actions
        assert ResolutionAction.SYNC in actions


# ---------------------------------------------------------------------------
# Manifest entry rules
# ---------------------------------------------------------------------------


class TestManifestEntryRules:
    """Tests for ManifestEntrySignal resolution rules."""

    def test_orphaned_sync_scaffolds_then_syncs(self):
        prov = _make_provider(manifest_entry=ManifestEntrySignal.ORPHANED)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "sync", provider="claude")
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.SCAFFOLD in actions
        assert ResolutionAction.SYNC in actions
        # Scaffold must precede sync
        assert actions.index(ResolutionAction.SCAFFOLD) < actions.index(
            ResolutionAction.SYNC
        )

    def test_untracked_install_adopts(self):
        prov = _make_provider(manifest_entry=ManifestEntrySignal.UNTRACKED)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "install", provider="claude")
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.ADOPT_DIRECTORY in actions

    def test_untracked_sync_no_force_warns(self):
        prov = _make_provider(manifest_entry=ManifestEntrySignal.UNTRACKED)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "sync", provider="claude", force=False)
        assert plan.steps == [] or all(
            s.action != ResolutionAction.ADOPT_DIRECTORY for s in plan.steps
        )
        assert any("untracked" in w.lower() for w in plan.warnings)

    def test_untracked_sync_force_adopts_then_syncs(self):
        prov = _make_provider(manifest_entry=ManifestEntrySignal.UNTRACKED)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "sync", provider="claude", force=True)
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.ADOPT_DIRECTORY in actions
        assert ResolutionAction.SYNC in actions


# ---------------------------------------------------------------------------
# Provider directory rules
# ---------------------------------------------------------------------------


class TestProviderDirRules:
    """Tests for ProviderDirSignal resolution rules."""

    def test_mixed_uninstall_no_force_conflicts(self):
        prov = _make_provider(dir_state=ProviderDirSignal.MIXED)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "uninstall", provider="claude", force=False)
        assert plan.blocked
        assert any("user-created content" in c.lower() for c in plan.conflicts)

    def test_mixed_uninstall_force_removes(self):
        prov = _make_provider(dir_state=ProviderDirSignal.MIXED)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "uninstall", provider="claude", force=True)
        assert not plan.blocked
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.REMOVE in actions

    def test_empty_sync_syncs(self):
        prov = _make_provider(dir_state=ProviderDirSignal.EMPTY)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "sync", provider="claude")
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.SYNC in actions

    def test_partial_sync_syncs(self):
        prov = _make_provider(dir_state=ProviderDirSignal.PARTIAL)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "sync", provider="claude")
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.SYNC in actions


# ---------------------------------------------------------------------------
# Content rules
# ---------------------------------------------------------------------------


class TestContentRules:
    """Tests for ContentSignal resolution rules."""

    def test_stale_sync_no_force_warns(self):
        prov = _make_provider(content={"old.md": ContentSignal.STALE})
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "sync", provider="claude", force=False)
        assert any("stale" in w.lower() for w in plan.warnings)
        assert all(s.action != ResolutionAction.PRUNE for s in plan.steps)

    def test_stale_sync_force_prunes(self):
        prov = _make_provider(content={"old.md": ContentSignal.STALE})
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "sync", provider="claude", force=True)
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.PRUNE in actions

    def test_missing_sync_syncs(self):
        prov = _make_provider(content={"new.md": ContentSignal.MISSING})
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "sync", provider="claude")
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.SYNC in actions

    def test_diverged_sync_no_force_warns(self):
        prov = _make_provider(content={"rule.md": ContentSignal.DIVERGED})
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "sync", provider="claude", force=False)
        assert any("diverged" in w.lower() for w in plan.warnings)

    def test_diverged_sync_force_overwrites(self):
        prov = _make_provider(content={"rule.md": ContentSignal.DIVERGED})
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "sync", provider="claude", force=True)
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.SYNC in actions

    def test_clean_content_no_steps(self):
        prov = _make_provider(content={"ok.md": ContentSignal.CLEAN})
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "sync", provider="claude")
        assert plan.steps == []
        assert plan.warnings == []


# ---------------------------------------------------------------------------
# Builtin version rules
# ---------------------------------------------------------------------------


class TestBuiltinVersionRules:
    """Tests for BuiltinVersionSignal resolution rules."""

    def test_modified_sync_no_force_warns(self):
        diag = _make_diagnosis(builtin_version=BuiltinVersionSignal.MODIFIED)
        plan = resolve(diag, "sync", force=False)
        assert any("modified" in w.lower() for w in plan.warnings)

    def test_modified_sync_force_reseeds(self):
        diag = _make_diagnosis(builtin_version=BuiltinVersionSignal.MODIFIED)
        plan = resolve(diag, "sync", force=True)
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.SYNC in actions
        assert any("re-seed" in s.reason.lower() for s in plan.steps)

    def test_no_snapshots_any_action_warns(self):
        for action in ("install", "sync", "uninstall"):
            diag = _make_diagnosis(
                builtin_version=BuiltinVersionSignal.NO_SNAPSHOTS,
                framework=FrameworkSignal.PRESENT,
            )
            plan = resolve(diag, action)
            assert any("no version baseline" in w.lower() for w in plan.warnings)


# ---------------------------------------------------------------------------
# Config rules
# ---------------------------------------------------------------------------


class TestConfigRules:
    """Tests for ConfigSignal resolution rules."""

    def test_missing_sync_syncs(self):
        prov = _make_provider(config=ConfigSignal.MISSING)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "sync", provider="claude")
        targets = [s.target for s in plan.steps]
        assert any("config" in t for t in targets)

    def test_foreign_sync_no_force_warns(self):
        prov = _make_provider(config=ConfigSignal.FOREIGN)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "sync", provider="claude", force=False)
        assert any("user-authored" in w.lower() for w in plan.warnings)

    def test_foreign_sync_force_overwrites(self):
        prov = _make_provider(config=ConfigSignal.FOREIGN)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "sync", provider="claude", force=True)
        targets = [s.target for s in plan.steps]
        assert any("config" in t for t in targets)


# ---------------------------------------------------------------------------
# Gitignore rules
# ---------------------------------------------------------------------------


class TestGitignoreRules:
    """Tests for GitignoreSignal resolution rules."""

    def test_no_entries_install_repairs(self):
        diag = _make_diagnosis(gitignore=GitignoreSignal.NO_ENTRIES)
        plan = resolve(diag, "install")
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.REPAIR_GITIGNORE in actions

    def test_corrupted_any_action_repairs(self):
        for action in ("install", "sync", "uninstall"):
            diag = _make_diagnosis(
                gitignore=GitignoreSignal.CORRUPTED,
                framework=FrameworkSignal.PRESENT,
            )
            plan = resolve(diag, action)
            actions = [s.action for s in plan.steps]
            assert ResolutionAction.REPAIR_GITIGNORE in actions

    def test_complete_no_action(self):
        diag = _make_diagnosis(gitignore=GitignoreSignal.COMPLETE)
        plan = resolve(diag, "install")
        gitignore_steps = [
            s for s in plan.steps if s.action == ResolutionAction.REPAIR_GITIGNORE
        ]
        assert gitignore_steps == []


# ---------------------------------------------------------------------------
# Provider filtering
# ---------------------------------------------------------------------------


class TestProviderFiltering:
    """Tests that provider= parameter filters correctly."""

    def test_all_providers_processed(self):
        providers = {
            Tool.CLAUDE: _make_provider(
                tool=Tool.CLAUDE, dir_state=ProviderDirSignal.EMPTY
            ),
            Tool.GEMINI: _make_provider(
                tool=Tool.GEMINI, dir_state=ProviderDirSignal.EMPTY
            ),
        }
        diag = _make_diagnosis(providers=providers)
        plan = resolve(diag, "sync", provider="all")
        targets = [s.target for s in plan.steps]
        assert any("claude" in t for t in targets)
        assert any("gemini" in t for t in targets)

    def test_single_provider_filtered(self):
        providers = {
            Tool.CLAUDE: _make_provider(
                tool=Tool.CLAUDE, dir_state=ProviderDirSignal.EMPTY
            ),
            Tool.GEMINI: _make_provider(
                tool=Tool.GEMINI, dir_state=ProviderDirSignal.EMPTY
            ),
        }
        diag = _make_diagnosis(providers=providers)
        plan = resolve(diag, "sync", provider="claude")
        targets = [s.target for s in plan.steps]
        assert any("claude" in t for t in targets)
        assert not any("gemini" in t for t in targets)


# ---------------------------------------------------------------------------
# ResolutionPlan.blocked property
# ---------------------------------------------------------------------------


class TestResolutionPlan:
    """Tests for ResolutionPlan dataclass behavior."""

    def test_blocked_when_conflicts(self):
        plan = ResolutionPlan(conflicts=["something"])
        assert plan.blocked is True

    def test_not_blocked_when_empty(self):
        plan = ResolutionPlan()
        assert plan.blocked is False

    def test_not_blocked_with_warnings_only(self):
        plan = ResolutionPlan(warnings=["minor issue"])
        assert plan.blocked is False


# ---------------------------------------------------------------------------
# CORRUPTED framework + uninstall
# ---------------------------------------------------------------------------


class TestCorruptedUninstall:
    def test_corrupted_uninstall_no_force_conflicts(self):
        diag = _make_diagnosis(framework=FrameworkSignal.CORRUPTED)
        plan = resolve(diag, "uninstall", force=False)
        assert plan.blocked
        assert any("corrupted" in c.lower() for c in plan.conflicts)

    def test_corrupted_uninstall_force_repairs(self):
        diag = _make_diagnosis(framework=FrameworkSignal.CORRUPTED)
        plan = resolve(diag, "uninstall", force=True)
        assert not plan.blocked
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.REPAIR_MANIFEST in actions


# ---------------------------------------------------------------------------
# BuiltinVersionSignal.DELETED
# ---------------------------------------------------------------------------


class TestBuiltinDeleted:
    def test_deleted_no_force_warns(self):
        diag = _make_diagnosis(builtin_version=BuiltinVersionSignal.DELETED)
        plan = resolve(diag, "sync", force=False)
        assert any("deleted" in w.lower() for w in plan.warnings)
        assert all(s.target != "builtins" for s in plan.steps)

    def test_deleted_force_sync_reseeds(self):
        diag = _make_diagnosis(builtin_version=BuiltinVersionSignal.DELETED)
        plan = resolve(diag, "sync", force=True)
        assert any("deleted" in w.lower() for w in plan.warnings)
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.SYNC in actions
        assert any(s.target == "builtins" for s in plan.steps)


# ---------------------------------------------------------------------------
# action="upgrade"
# ---------------------------------------------------------------------------


class TestUpgradeAction:
    def test_upgrade_missing_framework_proceeds(self):
        """Upgrade uses install semantics for framework: MISSING should proceed."""
        diag = _make_diagnosis(framework=FrameworkSignal.MISSING)
        plan = resolve(diag, "upgrade")
        assert not plan.blocked

    def test_upgrade_partial_provider_syncs(self):
        """Upgrade uses sync semantics for providers: PARTIAL should produce SYNC."""
        prov = _make_provider(dir_state=ProviderDirSignal.PARTIAL)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "upgrade", provider="claude")
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.SYNC in actions


# ---------------------------------------------------------------------------
# action="doctor"
# ---------------------------------------------------------------------------


class TestDoctorAction:
    def test_doctor_returns_empty_plan(self):
        """Doctor only diagnoses; it produces no steps, warnings, or conflicts."""
        prov = _make_provider(
            dir_state=ProviderDirSignal.EMPTY,
            manifest_entry=ManifestEntrySignal.ORPHANED,
        )
        diag = _make_diagnosis(
            framework=FrameworkSignal.CORRUPTED,
            gitignore=GitignoreSignal.CORRUPTED,
            providers={Tool.CLAUDE: prov},
        )
        plan = resolve(diag, "doctor")
        assert plan.steps == []
        assert plan.warnings == []
        assert plan.conflicts == []


# ---------------------------------------------------------------------------
# ORPHANED + install
# ---------------------------------------------------------------------------


class TestOrphanedInstall:
    def test_orphaned_install_scaffolds(self):
        prov = _make_provider(manifest_entry=ManifestEntrySignal.ORPHANED)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "install", provider="claude")
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.SCAFFOLD in actions


# ---------------------------------------------------------------------------
# UNTRACKED + uninstall
# ---------------------------------------------------------------------------


class TestUntrackedUninstall:
    def test_untracked_uninstall_no_force_conflicts(self):
        prov = _make_provider(manifest_entry=ManifestEntrySignal.UNTRACKED)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "uninstall", provider="claude", force=False)
        assert plan.blocked
        assert any("untracked" in c.lower() for c in plan.conflicts)

    def test_untracked_uninstall_force_removes(self):
        prov = _make_provider(manifest_entry=ManifestEntrySignal.UNTRACKED)
        diag = _make_diagnosis(providers={Tool.CLAUDE: prov})
        plan = resolve(diag, "uninstall", provider="claude", force=True)
        assert not plan.blocked
        actions = [s.action for s in plan.steps]
        assert ResolutionAction.REMOVE in actions
