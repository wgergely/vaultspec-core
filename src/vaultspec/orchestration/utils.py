"""Workspace utility helpers for path resolution and safe file access."""

from __future__ import annotations

import logging
import pathlib
from typing import Any

__all__ = ["SecurityError", "cleanup_subprocess_transports", "find_project_root", "kill_process_tree", "safe_read_text"]

logger = logging.getLogger(__name__)


async def cleanup_subprocess_transports(proc: Any) -> None:
    """Explicitly close all asyncio pipe transports on a subprocess.

    On Windows, the ProactorEventLoop can leak unclosed pipe transports
    (ResourceWarning / PytestUnraisableExceptionWarning) if a subprocess
    is killed or cancelled before the event loop can process the EOF.
    This helper explicitly aborts and closes them and yields to the event loop
    to allow pending connection_lost callbacks to gracefully finalize them.

    Args:
        proc: The asyncio.subprocess.Process instance.
    """
    import asyncio
    import contextlib

    def _cleanup_transport(transport: Any) -> None:
        if transport is None:
            return
        with contextlib.suppress(Exception):
            if hasattr(transport, "abort"):
                transport.abort()
        with contextlib.suppress(Exception):
            if hasattr(transport, "close"):
                transport.close()

    if getattr(proc, "stdin", None):
        _cleanup_transport(getattr(proc.stdin, "transport", None))
    if getattr(proc, "stdout", None):
        _cleanup_transport(getattr(proc.stdout, "_transport", None))
    if getattr(proc, "stderr", None):
        _cleanup_transport(getattr(proc.stderr, "_transport", None))
    _cleanup_transport(getattr(proc, "_transport", None))
            
    # Yield control to allow transport close callbacks to execute
    await asyncio.sleep(0)


def kill_process_tree(pid: int) -> None:
    """Kill a process and all its descendants.

    On Windows, proc.kill() kills only the bridge process;
    child processes become orphaned and persist indefinitely.
    taskkill /F /T kills the entire tree recursively.

    On Unix, orphaned children are reparented to PID 1 and eventually reaped
    by init/systemd, so no intervention is needed.

    Args:
        pid: Process ID of the root process to terminate.
    """
    import sys

    if sys.platform != "win32":
        return
    import subprocess

    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            timeout=5,
        )
    except Exception as exc:
        logger.debug("Process tree kill for PID %s failed: %s", pid, exc)


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
