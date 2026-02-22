"""Workspace utility helpers for path resolution and safe file access."""

from __future__ import annotations

import logging
import pathlib

__all__ = ["SecurityError", "find_project_root", "safe_read_text"]

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when a path access violates workspace boundaries."""

    pass


def find_project_root(start_dir: pathlib.Path | None = None) -> pathlib.Path:
    """Walk up from start_dir to find the git repository root.

    Security-critical: the nearest ``.git`` directory defines the workspace
    boundary used by ``safe_read_text``.  Falls back to ``start_dir`` itself
    when no ``.git`` is found (non-git usage).

    Args:
        start_dir: Directory to begin the search from.  Defaults to CWD.

    Returns:
        Resolved path to the project root.
    """
    candidate = (start_dir or pathlib.Path.cwd()).resolve()
    while candidate != candidate.parent:
        if (candidate / ".git").exists():
            logger.debug("Found project root at %s", candidate)
            return candidate
        candidate = candidate.parent
    # No .git found - fall back to start_dir (non-git usage)
    fallback = (start_dir or pathlib.Path.cwd()).resolve()
    logger.debug("No .git found, using start dir as project root: %s", fallback)
    return fallback


def safe_read_text(path: pathlib.Path, root_dir: pathlib.Path) -> str:
    """Read text from a path, raising an error if it falls outside the workspace.

    Args:
        path: The file path to read.
        root_dir: Workspace root; the resolved ``path`` must be a descendant.

    Returns:
        UTF-8 decoded file contents.

    Raises:
        SecurityError: If ``path`` resolves to a location outside ``root_dir``.
        FileNotFoundError: If ``path`` does not exist.
    """
    resolved_path = path.resolve()
    resolved_root = root_dir.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        msg = f"Attempted to access path outside workspace: {path}"
        logger.error("Security violation: %s", msg)
        raise SecurityError(msg)

    if not resolved_path.exists():
        logger.warning("File not found: %s", path)
        raise FileNotFoundError(f"File not found: {path}")
    logger.debug("Reading file: %s", path)
    return resolved_path.read_text(encoding="utf-8")
