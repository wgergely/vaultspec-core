from __future__ import annotations

import pathlib


class SecurityError(Exception):
    """Raised when a path access violates workspace boundaries."""

    pass


def find_project_root() -> pathlib.Path:
    """Walk up from CWD looking for the git repository root.

    Security-critical: uses CWD as the starting point and walks up to find
    the nearest .git directory, which defines the workspace boundary.
    """
    candidate = pathlib.Path.cwd().resolve()
    while candidate != candidate.parent:
        if (candidate / ".git").exists():
            return candidate
        candidate = candidate.parent
    # No .git found - fall back to CWD (non-git usage)
    return pathlib.Path.cwd().resolve()


def safe_read_text(path: pathlib.Path, root_dir: pathlib.Path) -> str:
    """Reads text from a path after verifying it is within the workspace."""
    resolved_path = path.resolve()
    resolved_root = root_dir.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        msg = f"Attempted to access path outside workspace: {path}"
        raise SecurityError(msg)

    if not resolved_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return resolved_path.read_text(encoding="utf-8")
