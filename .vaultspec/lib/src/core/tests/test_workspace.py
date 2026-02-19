"""Unit tests for core.workspace — layout resolution and git detection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from core.workspace import (
    LayoutMode,
    WorkspaceError,
    discover_git,
    resolve_workspace,
)

# ---------------------------------------------------------------------------
# Helpers to scaffold filesystem fixtures
# ---------------------------------------------------------------------------


def _make_framework(root: Path, fw_name: str = ".vaultspec") -> Path:
    """Create a minimal framework directory structure."""
    fw = root / fw_name
    (fw / "lib" / "src").mkdir(parents=True)
    (fw / "lib" / "scripts").mkdir(parents=True)
    (fw / "rules").mkdir(parents=True)
    return fw


def _make_git_dir(root: Path) -> Path:
    """Create a standard .git/ directory with enough structure to look real."""
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    (git_dir / "refs").mkdir()
    (git_dir / "objects").mkdir()
    return git_dir


def _make_git_file(worktree: Path, gitdir_target: Path) -> Path:
    """Create a .git file (linked worktree pointer)."""
    git_file = worktree / ".git"
    git_file.write_text(f"gitdir: {gitdir_target}\n")
    return git_file


# ---------------------------------------------------------------------------
# discover_git tests
# ---------------------------------------------------------------------------


class TestDiscoverGit:
    """Tests for the git detection function."""

    def test_standard_git_directory(self, tmp_path: Path) -> None:
        _make_git_dir(tmp_path)

        info = discover_git(tmp_path)

        assert info is not None
        assert info.repo_root == tmp_path
        assert info.is_worktree is False
        assert info.is_bare is False
        assert info.container_root is None

    def test_no_git(self, tmp_path: Path) -> None:
        info = discover_git(tmp_path)
        assert info is None

    def test_git_file_linked_worktree(self, tmp_path: Path) -> None:
        # Main repo with .git/worktrees/<name>/
        main_repo = tmp_path / "main-repo"
        main_repo.mkdir()
        git_dir = _make_git_dir(main_repo)
        worktrees_dir = git_dir / "worktrees" / "feature-branch"
        worktrees_dir.mkdir(parents=True)

        # Linked worktree directory
        wt = tmp_path / "feature-branch"
        wt.mkdir()
        _make_git_file(wt, worktrees_dir)

        info = discover_git(wt)

        assert info is not None
        assert info.is_worktree is True
        assert info.repo_root == main_repo
        assert info.worktree_root == wt

    def test_container_mode_gt_directory(self, tmp_path: Path) -> None:
        # Container with .gt/ bare repo
        gt = tmp_path / ".gt"
        gt.mkdir()
        (gt / "HEAD").write_text("ref: refs/heads/main\n")

        info = discover_git(tmp_path)

        assert info is not None
        assert info.is_bare is True
        assert info.container_root == tmp_path
        assert info.repo_root == tmp_path

    def test_container_mode_cwd_in_worktree(self, tmp_path: Path) -> None:
        # Container root with .gt/
        gt = tmp_path / ".gt"
        gt.mkdir()
        (gt / "HEAD").write_text("ref: refs/heads/main\n")
        wt_git_dir = gt / "worktrees" / "feature"
        wt_git_dir.mkdir(parents=True)

        # Worktree directory with .git file pointing into .gt/
        wt = tmp_path / "feature"
        wt.mkdir()
        _make_git_file(wt, wt_git_dir)

        # discover_git from the worktree should find .gt/ walking up
        info = discover_git(wt)

        assert info is not None
        assert info.container_root == tmp_path
        assert info.is_bare is True

    def test_walks_up_directories(self, tmp_path: Path) -> None:
        _make_git_dir(tmp_path)
        subdir = tmp_path / "a" / "b" / "c"
        subdir.mkdir(parents=True)

        info = discover_git(subdir)

        assert info is not None
        assert info.repo_root == tmp_path

    def test_git_file_with_relative_path(self, tmp_path: Path) -> None:
        main_repo = tmp_path / "repo"
        main_repo.mkdir()
        git_dir = _make_git_dir(main_repo)
        wt_dir = git_dir / "worktrees" / "wt1"
        wt_dir.mkdir(parents=True)

        wt = tmp_path / "wt1"
        wt.mkdir()
        # Write a relative gitdir pointer
        (wt / ".git").write_text("gitdir: ../repo/.git/worktrees/wt1\n")

        info = discover_git(wt)

        assert info is not None
        assert info.is_worktree is True
        assert info.repo_root == main_repo


# ---------------------------------------------------------------------------
# resolve_workspace tests
# ---------------------------------------------------------------------------


class TestResolveWorkspace:
    """Tests for the workspace layout resolution function."""

    def test_explicit_mode_both_overrides(self, tmp_path: Path) -> None:
        content = tmp_path / "content"
        output = tmp_path / "output"
        fw = _make_framework(content)
        output.mkdir()

        layout = resolve_workspace(
            root_override=output,
            content_override=content,
            framework_root=fw,
            cwd=tmp_path,
        )

        assert layout.mode == LayoutMode.EXPLICIT
        assert layout.content_root == content
        assert layout.output_root == output
        assert layout.vault_root == output / ".vault"
        assert layout.framework_root == fw

    def test_standalone_root_override_only(self, tmp_path: Path) -> None:
        root = tmp_path / "project"
        fw = _make_framework(root)
        root.mkdir(exist_ok=True)

        layout = resolve_workspace(
            root_override=root,
            framework_root=fw,
            cwd=tmp_path,
        )

        assert layout.mode == LayoutMode.STANDALONE
        assert layout.content_root == root / ".vaultspec"
        assert layout.output_root == root
        assert layout.vault_root == root / ".vault"

    def test_standalone_classic_git(self, tmp_path: Path) -> None:
        fw = _make_framework(tmp_path)
        _make_git_dir(tmp_path)

        layout = resolve_workspace(
            framework_root=fw,
            cwd=tmp_path,
        )

        assert layout.mode == LayoutMode.STANDALONE
        assert layout.git is not None
        assert layout.git.is_worktree is False
        assert layout.output_root == tmp_path
        assert layout.content_root == tmp_path / ".vaultspec"

    def test_standalone_container_git(self, tmp_path: Path) -> None:
        # Container root
        fw = _make_framework(tmp_path)
        gt = tmp_path / ".gt"
        gt.mkdir()
        (gt / "HEAD").write_text("ref: refs/heads/main\n")

        layout = resolve_workspace(
            framework_root=fw,
            cwd=tmp_path,
        )

        assert layout.mode == LayoutMode.STANDALONE
        assert layout.git is not None
        assert layout.git.container_root == tmp_path
        assert layout.output_root == tmp_path
        assert layout.content_root == tmp_path / ".vaultspec"

    def test_standalone_linked_worktree(self, tmp_path: Path) -> None:
        # Main repo
        main_repo = tmp_path / "main-repo"
        fw = _make_framework(main_repo)
        git_dir = _make_git_dir(main_repo)
        wt_git = git_dir / "worktrees" / "feature"
        wt_git.mkdir(parents=True)

        # Worktree
        wt = tmp_path / "feature"
        wt.mkdir()
        _make_git_file(wt, wt_git)

        layout = resolve_workspace(
            framework_root=fw,
            cwd=wt,
        )

        assert layout.mode == LayoutMode.STANDALONE
        assert layout.git is not None
        assert layout.git.is_worktree is True
        assert layout.output_root == main_repo

    def test_no_git_structural_fallback(self, tmp_path: Path) -> None:
        fw = _make_framework(tmp_path)

        layout = resolve_workspace(
            framework_root=fw,
            cwd=tmp_path,
        )

        assert layout.mode == LayoutMode.STANDALONE
        assert layout.git is None
        assert layout.output_root == tmp_path
        assert layout.framework_root == fw

    def test_vault_root_always_follows_output(self, tmp_path: Path) -> None:
        content = tmp_path / "content"
        output = tmp_path / "output"
        fw = _make_framework(content)
        output.mkdir()

        layout = resolve_workspace(
            root_override=output,
            content_override=content,
            framework_root=fw,
        )

        assert layout.vault_root == output / ".vault"

    def test_framework_root_from_structural_not_env(self, tmp_path: Path) -> None:
        root = tmp_path / "project"
        fw = _make_framework(root)

        layout = resolve_workspace(
            root_override=root,
            framework_root=fw,
            cwd=tmp_path,
        )

        assert layout.framework_root == fw

    def test_validation_missing_content_root(self, tmp_path: Path) -> None:
        output = tmp_path / "output"
        output.mkdir()
        fw = _make_framework(tmp_path / "framework-source")

        with pytest.raises(WorkspaceError, match="content_root"):
            resolve_workspace(
                root_override=output,
                content_override=tmp_path / "nonexistent",
                framework_root=fw,
            )

    def test_validation_missing_framework_lib(self, tmp_path: Path) -> None:
        root = tmp_path / "project"
        root.mkdir()
        # Create .vaultspec/ but NOT .vaultspec/lib/
        bad_fw = root / ".vaultspec"
        bad_fw.mkdir()

        with pytest.raises(WorkspaceError, match="framework_root/lib"):
            resolve_workspace(
                root_override=root,
                framework_root=bad_fw,
            )

    def test_custom_framework_dir_name(self, tmp_path: Path) -> None:
        root = tmp_path / "project"
        fw = _make_framework(root, fw_name=".custom-fw")

        layout = resolve_workspace(
            root_override=root,
            framework_dir_name=".custom-fw",
            framework_root=fw,
            cwd=tmp_path,
        )

        assert layout.content_root == root / ".custom-fw"

    def test_explicit_mode_without_framework_root_validates(
        self, tmp_path: Path
    ) -> None:
        """EXPLICIT mode without framework_root falls back to content/.vaultspec,
        which won't have lib/ — validation should catch this with a clear message."""
        content = tmp_path / "content"
        output = tmp_path / "output"
        content.mkdir()
        output.mkdir()

        with pytest.raises(WorkspaceError, match="framework_root/lib"):
            resolve_workspace(
                root_override=output,
                content_override=content,
                # framework_root intentionally omitted
            )

    def test_explicit_mode_with_framework_root_succeeds(self, tmp_path: Path) -> None:
        """EXPLICIT mode with framework_root provided bypasses the fallback."""
        content = tmp_path / "content"
        output = tmp_path / "output"
        fw = _make_framework(tmp_path / "fw-source")
        content.mkdir()
        output.mkdir()

        layout = resolve_workspace(
            root_override=output,
            content_override=content,
            framework_root=fw,
        )

        assert layout.mode == LayoutMode.EXPLICIT
        assert layout.framework_root == fw

    def test_content_override_only_with_git(self, tmp_path: Path) -> None:
        """content_override alone derives output_root from git."""
        project = tmp_path / "project"
        project.mkdir()
        fw = _make_framework(project)
        _make_git_dir(project)

        separate_content = tmp_path / "my-content"
        separate_content.mkdir()

        layout = resolve_workspace(
            content_override=separate_content,
            framework_root=fw,
            cwd=project,
        )

        assert layout.mode == LayoutMode.EXPLICIT
        assert layout.content_root == separate_content
        assert layout.output_root == project
        assert layout.git is not None

    def test_content_override_only_structural_fallback(self, tmp_path: Path) -> None:
        """content_override alone falls back to framework_root.parent for output."""
        fw = _make_framework(tmp_path)

        separate_content = tmp_path / "content-src"
        separate_content.mkdir()

        layout = resolve_workspace(
            content_override=separate_content,
            framework_root=fw,
            cwd=tmp_path / "unrelated",
        )

        assert layout.mode == LayoutMode.EXPLICIT
        assert layout.content_root == separate_content
        assert layout.output_root == tmp_path

    def test_content_override_only_cwd_fallback(self, tmp_path: Path) -> None:
        """content_override with no git and no framework_root uses cwd."""
        content = tmp_path / "content"
        content.mkdir()
        # Need framework lib for validation
        fw = _make_framework(content)

        layout = resolve_workspace(
            content_override=content,
            framework_root=fw,
            cwd=tmp_path,
        )

        assert layout.mode == LayoutMode.EXPLICIT
        assert layout.content_root == content

    def test_validation_output_root_parent_missing(self, tmp_path: Path) -> None:
        """output_root.parent validation catches non-existent parent."""
        fw = _make_framework(tmp_path / "content")

        with pytest.raises(WorkspaceError, match="output_root parent"):
            resolve_workspace(
                root_override=tmp_path / "nonexistent" / "deeply" / "nested",
                content_override=tmp_path / "content",
                framework_root=fw,
            )

    def test_frozen_layout(self, tmp_path: Path) -> None:
        fw = _make_framework(tmp_path)
        _make_git_dir(tmp_path)

        layout = resolve_workspace(
            framework_root=fw,
            cwd=tmp_path,
        )

        with pytest.raises(AttributeError):
            layout.output_root = tmp_path / "changed"  # type: ignore[misc]
