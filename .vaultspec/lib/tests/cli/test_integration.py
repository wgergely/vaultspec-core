from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

import cli
import pytest
from core.workspace import LayoutMode, WorkspaceError, resolve_workspace

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration]


def test_cli_help():
    result = subprocess.run(
        [sys.executable, ".vaultspec/lib/scripts/subagent.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage: subagent.py" in result.stdout


def test_cli_list_agents():
    result = subprocess.run(
        [sys.executable, ".vaultspec/lib/scripts/subagent.py", "list"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # Output should at least be valid JSON or a list of agents
    assert "agents" in result.stdout or "[]" in result.stdout


# ---------------------------------------------------------------------------
# --content-dir CLI integration
# ---------------------------------------------------------------------------


class TestContentDirCLI:
    """Verify --content-dir routes content from a separate directory."""

    def _make_content_dir(self, base: Path) -> Path:
        """Create a standalone content directory with rules."""
        content = base / "custom-content"
        (content / "rules" / "rules").mkdir(parents=True)
        (content / "rules" / "agents").mkdir(parents=True)
        (content / "rules" / "skills").mkdir(parents=True)
        (content / "rules" / "system").mkdir(parents=True)
        # Write a test rule
        rule = content / "rules" / "rules" / "test-rule.md"
        rule.write_text(
            "---\nname: test-rule\ntrigger: always_on\n---\n\nTest rule body.\n",
            encoding="utf-8",
        )
        return content

    def test_init_paths_uses_content_root(self, tmp_path: Path) -> None:
        """init_paths() with a split layout points source dirs at content_root."""
        from core.workspace import LayoutMode, WorkspaceLayout

        content = self._make_content_dir(tmp_path)
        output = tmp_path / "output"
        output.mkdir()
        # Need framework lib for real usage, but init_paths only reads layout
        fw = tmp_path / "fw"
        (fw / "lib" / "src").mkdir(parents=True)
        (fw / "lib" / "scripts").mkdir(parents=True)

        layout = WorkspaceLayout(
            content_root=content,
            output_root=output,
            vault_root=output / ".vault",
            framework_root=fw,
            mode=LayoutMode.EXPLICIT,
            git=None,
        )

        cli.init_paths(layout)

        assert output == cli.ROOT_DIR
        assert content / "rules" / "rules" == cli.RULES_SRC_DIR
        assert content / "rules" / "agents" == cli.AGENTS_SRC_DIR
        assert content / "rules" / "skills" == cli.SKILLS_SRC_DIR

    def test_collect_rules_from_separate_content(self, tmp_path: Path) -> None:
        """Rules are collected from the content dir, not the output dir."""
        from core.workspace import LayoutMode, WorkspaceLayout

        content = self._make_content_dir(tmp_path)
        output = tmp_path / "output"
        output.mkdir()
        fw = tmp_path / "fw"
        (fw / "lib" / "src").mkdir(parents=True)
        (fw / "lib" / "scripts").mkdir(parents=True)

        layout = WorkspaceLayout(
            content_root=content,
            output_root=output,
            vault_root=output / ".vault",
            framework_root=fw,
            mode=LayoutMode.EXPLICIT,
            git=None,
        )

        cli.init_paths(layout)

        # Ensure destination dirs exist
        for d in [".claude/rules", ".gemini/rules", ".agent/rules"]:
            (output / d).mkdir(parents=True, exist_ok=True)

        sources = cli.collect_rules()
        assert "test-rule.md" in sources


# ---------------------------------------------------------------------------
# _paths.py env var bridge
# ---------------------------------------------------------------------------


class TestPathsEnvBridge:
    """Verify resolve_workspace honours env-var-sourced overrides."""

    def test_content_override_env_var(self, tmp_path: Path) -> None:
        """Simulates VAULTSPEC_CONTENT_DIR being set via _paths.py bridge."""
        project = tmp_path / "project"
        project.mkdir()
        # Create framework structure in project (for framework_root)
        fw = project / ".vaultspec"
        (fw / "lib" / "src").mkdir(parents=True)
        (fw / "lib" / "scripts").mkdir(parents=True)
        (fw / "rules").mkdir(parents=True)

        # Separate content directory
        content = tmp_path / "shared-content"
        content.mkdir()

        layout = resolve_workspace(
            root_override=project,
            content_override=content,
            framework_root=fw,
        )

        assert layout.mode == LayoutMode.EXPLICIT
        assert layout.content_root == content
        assert layout.output_root == project

    def test_content_override_without_root_override(self, tmp_path: Path) -> None:
        """VAULTSPEC_CONTENT_DIR without VAULTSPEC_ROOT_DIR uses git/fallback."""
        project = tmp_path / "repo"
        project.mkdir()
        fw = project / ".vaultspec"
        (fw / "lib" / "src").mkdir(parents=True)
        (fw / "lib" / "scripts").mkdir(parents=True)
        (fw / "rules").mkdir(parents=True)

        content = tmp_path / "content-only"
        content.mkdir()

        layout = resolve_workspace(
            content_override=content,
            framework_root=fw,
            cwd=project,
        )

        assert layout.mode == LayoutMode.EXPLICIT
        assert layout.content_root == content
        # output_root derived from structural fallback (framework_root.parent)
        assert layout.output_root == project


# ---------------------------------------------------------------------------
# Validation edge cases
# ---------------------------------------------------------------------------


class TestValidationEdgeCases:
    """Test validation branches in resolve_workspace."""

    def test_output_root_parent_must_exist(self, tmp_path: Path) -> None:
        """Setting root_override to path whose parent doesn't exist fails."""
        fw = tmp_path / "fw"
        (fw / "lib" / "src").mkdir(parents=True)
        (fw / "lib" / "scripts").mkdir(parents=True)

        content = tmp_path / "content"
        content.mkdir()

        with pytest.raises(WorkspaceError, match="output_root parent"):
            resolve_workspace(
                root_override=tmp_path / "missing_parent" / "output",
                content_override=content,
                framework_root=fw,
            )
