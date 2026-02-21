"""Three-path workspace layout resolution with git-aware detection.

Resolves ``content_root``, ``output_root``, ``vault_root``, and
``framework_root`` from a combination of explicit overrides (env vars /
CLI flags), git repository detection, and structural fallbacks.

**Stdlib only** -- no external dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "GitInfo",
    "LayoutMode",
    "WorkspaceError",
    "WorkspaceLayout",
    "discover_git",
    "resolve_workspace",
]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class LayoutMode(Enum):
    """How VaultSpec was invoked and where paths point."""

    STANDALONE = "standalone"
    EXPLICIT = "explicit"


@dataclass(frozen=True)
class GitInfo:
    """Discovered git repository metadata."""

    git_dir: Path
    repo_root: Path
    is_worktree: bool
    is_bare: bool
    worktree_root: Path | None
    container_root: Path | None


@dataclass(frozen=True)
class WorkspaceLayout:
    """Fully resolved, validated workspace paths."""

    content_root: Path
    output_root: Path
    vault_root: Path
    framework_root: Path
    mode: LayoutMode
    git: GitInfo | None


# ---------------------------------------------------------------------------
# Git detection helpers
# ---------------------------------------------------------------------------


def _strip_unc(path: Path) -> Path:
    """Strip Windows ``\\\\?\\`` UNC prefix if present."""
    s = str(path)
    if s.startswith("\\\\?\\"):
        return Path(s[4:])
    return path


def _parse_git_pointer(git_path: Path) -> Path | None:
    """Parse a ``.git`` file containing ``gitdir: <path>``.

    Returns the resolved absolute path to the git directory, or ``None``
    if the file does not contain a valid pointer.
    """
    try:
        content = git_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None

    if not content.startswith("gitdir:"):
        return None

    raw = content[len("gitdir:") :].strip()
    target = Path(raw)

    if not target.is_absolute():
        target = (git_path.parent / target).resolve()
    else:
        target = target.resolve()

    return _strip_unc(target)


def _walk_up_for_git(start: Path) -> tuple[Path, bool] | None:
    """Walk up from *start* looking for ``.git`` (file or directory).

    Returns ``(dot_git_path, is_file)`` or ``None``.
    """
    current = start.resolve()
    current = _strip_unc(current)

    while True:
        dot_git = current / ".git"
        if dot_git.exists():
            return (dot_git, dot_git.is_file())

        parent = current.parent
        if parent == current:
            break
        current = parent

    return None


def _find_container_root(git_dir: Path) -> Path | None:
    """Given a resolved git_dir inside a ``.gt/`` bare repo, return the
    container root (the parent of ``.gt/``).

    Handles both direct ``.gt/`` refs and ``.gt/worktrees/<name>/``
    sub-paths.
    """
    parts = git_dir.parts
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == ".gt":
            return Path(*parts[:i]) if i > 0 else Path(parts[0])
    return None


def discover_git(start: Path) -> GitInfo | None:
    """Walk up from *start* to find and classify the git repository.

    Handles: standard repos (``.git/`` dir), linked worktrees (``.git``
    file with gitdir pointer), container mode (``.gt/`` bare repo), and
    bare repos.
    """
    resolved_start = _strip_unc(start.resolve())

    # --- Check for .gt/ container at start or walking up ---
    current = resolved_start
    while True:
        gt = current / ".gt"
        if gt.is_dir():
            return GitInfo(
                git_dir=gt,
                repo_root=current,
                is_worktree=False,
                is_bare=True,
                worktree_root=None,
                container_root=current,
            )
        parent = current.parent
        if parent == current:
            break
        current = parent

    # --- Check for .git (file or directory) ---
    result = _walk_up_for_git(resolved_start)
    if result is None:
        return None

    dot_git, is_file = result

    if not is_file:
        # Standard .git/ directory
        return GitInfo(
            git_dir=dot_git,
            repo_root=dot_git.parent,
            is_worktree=False,
            is_bare=False,
            worktree_root=None,
            container_root=None,
        )

    # .git is a file -- linked worktree
    real_git_dir = _parse_git_pointer(dot_git)
    if real_git_dir is None:
        return None

    worktree_root = dot_git.parent

    # Check if this points into a .gt/ bare repo (container mode)
    container = _find_container_root(real_git_dir)
    if container is not None:
        return GitInfo(
            git_dir=real_git_dir,
            repo_root=container,
            is_worktree=True,
            is_bare=True,
            worktree_root=worktree_root,
            container_root=container,
        )

    # Standard linked worktree -- trace back to main repo root.
    # real_git_dir is typically <repo>/.git/worktrees/<name>
    # The main repo root is the grandparent of the ``worktrees/`` dir.
    if real_git_dir.parent.name == "worktrees":
        main_git_dir = real_git_dir.parent.parent
        return GitInfo(
            git_dir=real_git_dir,
            repo_root=main_git_dir.parent,
            is_worktree=True,
            is_bare=False,
            worktree_root=worktree_root,
            container_root=None,
        )

    # Fallback: cannot determine main repo root from pointer
    return GitInfo(
        git_dir=real_git_dir,
        repo_root=worktree_root,
        is_worktree=True,
        is_bare=False,
        worktree_root=worktree_root,
        container_root=None,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class WorkspaceError(Exception):
    """Raised when workspace layout validation fails."""


def _validate(layout: WorkspaceLayout) -> None:
    """Validate a resolved ``WorkspaceLayout``.

    Raises :class:`WorkspaceError` with actionable messages.
    """
    if not layout.content_root.is_dir():
        raise WorkspaceError(
            f"content_root does not exist or is not a directory: "
            f"{layout.content_root}\n"
            f"Set VAULTSPEC_CONTENT_DIR to the directory containing "
            f"rules/agents/, rules/skills/."
        )

    if not layout.output_root.parent.exists():
        raise WorkspaceError(
            f"output_root parent does not exist: {layout.output_root.parent}\n"
            f"Set VAULTSPEC_ROOT_DIR to a valid output directory."
        )


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_workspace(
    *,
    root_override: Path | None = None,
    content_override: Path | None = None,
    framework_dir_name: str = ".vaultspec",
    framework_root: Path | None = None,
    cwd: Path | None = None,
) -> WorkspaceLayout:
    """Resolve the complete workspace layout.

    Parameters
    ----------
    root_override:
        Explicit output root (``--root`` / ``VAULTSPEC_ROOT_DIR``).
    content_override:
        Explicit content root (``--content-dir`` / ``VAULTSPEC_CONTENT_DIR``).
    framework_dir_name:
        Name of the framework directory (default ``".vaultspec"``).
    framework_root:
        Structurally-known location of the ``.vaultspec/`` directory
        containing Python code. Passed from ``_paths.py``, never derived
        from env vars.
    cwd:
        Override for ``Path.cwd()`` (testing).
    """
    effective_cwd = (cwd or Path.cwd()).resolve()
    effective_cwd = _strip_unc(effective_cwd)

    # --- EXPLICIT mode: both content + root provided ---
    if content_override is not None and root_override is not None:
        content_root = content_override.resolve()
        output_root = root_override.resolve()
        content_root = _strip_unc(content_root)
        output_root = _strip_unc(output_root)

        fw_root = framework_root or (content_root / framework_dir_name)

        layout = WorkspaceLayout(
            content_root=content_root,
            output_root=output_root,
            vault_root=output_root / ".vault",
            framework_root=fw_root,
            mode=LayoutMode.EXPLICIT,
            git=None,
        )
        _validate(layout)
        return layout

    # --- EXPLICIT mode: only content override (derive output_root) ---
    if content_override is not None:
        content_root = _strip_unc(content_override.resolve())
        fw_root = framework_root or (content_root / framework_dir_name)

        # Derive output_root from git or structural fallback
        git = discover_git(effective_cwd)
        if git is not None:
            root = _strip_unc(
                git.container_root if git.container_root is not None else git.repo_root
            )
        elif framework_root is not None:
            root = _strip_unc(framework_root.parent)
            git = None
        else:
            root = effective_cwd
            git = None

        layout = WorkspaceLayout(
            content_root=content_root,
            output_root=root,
            vault_root=root / ".vault",
            framework_root=fw_root,
            mode=LayoutMode.EXPLICIT,
            git=git,
        )
        _validate(layout)
        return layout

    # --- STANDALONE: only root override ---
    if root_override is not None:
        root = root_override.resolve()
        root = _strip_unc(root)
        fw_root = framework_root or (root / framework_dir_name)

        layout = WorkspaceLayout(
            content_root=root / framework_dir_name,
            output_root=root,
            vault_root=root / ".vault",
            framework_root=fw_root,
            mode=LayoutMode.STANDALONE,
            git=None,
        )
        _validate(layout)
        return layout

    # --- No overrides: try git detection ---
    git = discover_git(effective_cwd)

    if git is not None:
        # Container/worktree mode: use container_root if available
        root = git.container_root if git.container_root is not None else git.repo_root

        root = _strip_unc(root)
        fw_root = framework_root or (root / framework_dir_name)

        layout = WorkspaceLayout(
            content_root=root / framework_dir_name,
            output_root=root,
            vault_root=root / ".vault",
            framework_root=fw_root,
            mode=LayoutMode.STANDALONE,
            git=git,
        )
        _validate(layout)
        return layout

    # --- Structural fallback: derive from framework_root ---
    if framework_root is not None:
        root = framework_root.parent
        root = _strip_unc(root)

        layout = WorkspaceLayout(
            content_root=framework_root,
            output_root=root,
            vault_root=root / ".vault",
            framework_root=framework_root,
            mode=LayoutMode.STANDALONE,
            git=None,
        )
        _validate(layout)
        return layout

    # --- Last resort: cwd-based ---
    root = effective_cwd
    fw_root = root / framework_dir_name

    layout = WorkspaceLayout(
        content_root=fw_root,
        output_root=root,
        vault_root=root / ".vault",
        framework_root=fw_root,
        mode=LayoutMode.STANDALONE,
        git=None,
    )
    _validate(layout)
    return layout
