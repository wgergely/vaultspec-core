"""Tests for the resolution plan executor.

Every test creates real filesystem state, executes real steps,
and asserts real filesystem changes. No mocks.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.core.diagnosis.signals import ResolutionAction
from vaultspec_core.core.executor import execute_plan
from vaultspec_core.core.gitignore import MARKER_BEGIN
from vaultspec_core.core.manifest import read_manifest_data
from vaultspec_core.core.resolver import ResolutionPlan, ResolutionStep

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a fully installed workspace for testing."""
    from vaultspec_core.core.commands import install_run

    (tmp_path / ".gitignore").write_text("# user\n", encoding="utf-8")
    install_run(path=tmp_path, provider="all")
    return tmp_path


class TestRepairManifest:
    """REPAIR_MANIFEST handler rebuilds manifest from directory presence."""

    def test_corrupted_manifest_repaired(self, workspace: Path) -> None:
        """Corrupt the manifest, execute REPAIR_MANIFEST, verify it's valid."""
        manifest_path = workspace / ".vaultspec" / "providers.json"
        manifest_path.write_text("CORRUPT", encoding="utf-8")

        step = ResolutionStep(
            action=ResolutionAction.REPAIR_MANIFEST,
            target="manifest",
            reason="test",
        )
        plan = ResolutionPlan(steps=[step])
        result = execute_plan(plan, workspace, preflight_only=False)

        assert result.all_succeeded
        mdata = read_manifest_data(workspace)
        assert "claude" in mdata.installed

    def test_repair_detects_providers_from_dirs(self, workspace: Path) -> None:
        """Delete a provider dir, repair manifest, verify it's excluded."""
        shutil.rmtree(workspace / ".claude")

        manifest_path = workspace / ".vaultspec" / "providers.json"
        manifest_path.write_text("CORRUPT", encoding="utf-8")

        step = ResolutionStep(
            action=ResolutionAction.REPAIR_MANIFEST,
            target="manifest",
            reason="test",
        )
        plan = ResolutionPlan(steps=[step])
        result = execute_plan(plan, workspace, preflight_only=False)

        assert result.all_succeeded
        mdata = read_manifest_data(workspace)
        assert "claude" not in mdata.installed
        assert "gemini" in mdata.installed


class TestScaffold:
    """SCAFFOLD handler recreates provider directories."""

    def test_scaffold_creates_provider_dirs(self, workspace: Path) -> None:
        """Delete provider dir, scaffold it, verify dirs created."""
        shutil.rmtree(workspace / ".claude")
        assert not (workspace / ".claude").exists()

        step = ResolutionStep(
            action=ResolutionAction.SCAFFOLD,
            target="claude",
            reason="test",
        )
        plan = ResolutionPlan(steps=[step])
        result = execute_plan(plan, workspace, preflight_only=False)

        assert result.all_succeeded
        assert (workspace / ".claude").exists()
        assert (workspace / ".claude" / "rules").exists()


class TestAdoptDirectory:
    """ADOPT_DIRECTORY handler registers untracked dirs in the manifest."""

    def test_adopt_adds_to_manifest(self, workspace: Path) -> None:
        """Remove provider from manifest but leave dir, adopt it."""
        from vaultspec_core.core.manifest import remove_provider

        remove_provider(workspace, "claude")
        mdata = read_manifest_data(workspace)
        assert "claude" not in mdata.installed

        step = ResolutionStep(
            action=ResolutionAction.ADOPT_DIRECTORY,
            target="claude",
            reason="test",
        )
        plan = ResolutionPlan(steps=[step])
        result = execute_plan(plan, workspace, preflight_only=False)

        assert result.all_succeeded
        mdata = read_manifest_data(workspace)
        assert "claude" in mdata.installed


class TestRepairGitignore:
    """REPAIR_GITIGNORE handler restores the managed block."""

    def test_repair_adds_missing_block(self, workspace: Path) -> None:
        """Remove gitignore block, repair, verify block is back."""
        from vaultspec_core.core.enums import ManagedState
        from vaultspec_core.core.gitignore import ensure_gitignore_block

        ensure_gitignore_block(workspace, [], state=ManagedState.ABSENT)
        gi = workspace / ".gitignore"
        assert MARKER_BEGIN not in gi.read_text(encoding="utf-8")

        step = ResolutionStep(
            action=ResolutionAction.REPAIR_GITIGNORE,
            target=".gitignore",
            reason="test",
        )
        plan = ResolutionPlan(steps=[step])
        result = execute_plan(plan, workspace, preflight_only=False)

        assert result.all_succeeded
        assert MARKER_BEGIN in gi.read_text(encoding="utf-8")


class TestDryRun:
    """dry_run=True records steps as succeeded without modifying the filesystem."""

    def test_dry_run_no_filesystem_changes(self, workspace: Path) -> None:
        manifest_path = workspace / ".vaultspec" / "providers.json"
        manifest_path.write_text("CORRUPT", encoding="utf-8")

        step = ResolutionStep(
            action=ResolutionAction.REPAIR_MANIFEST,
            target="manifest",
            reason="test",
        )
        plan = ResolutionPlan(steps=[step])
        result = execute_plan(plan, workspace, dry_run=True, preflight_only=False)

        assert result.all_succeeded
        assert manifest_path.read_text(encoding="utf-8") == "CORRUPT"


class TestErrorCollection:
    """Executor collects errors and continues executing remaining steps."""

    def test_failure_records_but_continues(self, workspace: Path) -> None:
        """First step fails, second still runs."""
        steps = [
            ResolutionStep(
                action=ResolutionAction.SCAFFOLD,
                target="nonexistent_provider",
                reason="scaffold nonexistent",
            ),
            ResolutionStep(
                action=ResolutionAction.REPAIR_GITIGNORE,
                target=".gitignore",
                reason="fix gitignore",
            ),
        ]
        plan = ResolutionPlan(steps=steps)
        result = execute_plan(plan, workspace, preflight_only=False)

        assert not result.all_succeeded
        assert len(result.results) == 2
        assert result.results[1].success
