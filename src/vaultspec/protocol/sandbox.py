"""Shared sandboxing utilities for agent executors.

Provides file-write restriction callbacks used by both the ACP bridge
(``protocol.acp.claude_bridge``) and the A2A executors
(``protocol.a2a.executors``).
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

logger = logging.getLogger(__name__)

__all__ = ["_SHELL_TOOLS", "_WRITE_TOOLS", "_is_vault_path", "_make_sandbox_callback"]

# Tools that perform file writes in Claude Code
_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_SHELL_TOOLS = frozenset({"Bash"})


def _is_vault_path(file_path: str, root_dir: str) -> bool:
    """Return True if *file_path* is inside ``<root_dir>/.vault/``.

    Args:
        file_path: Absolute or relative path to check.
        root_dir: Project root directory used as the resolution base.

    Returns:
        True if the resolved path is ``.vault/`` or a descendant of it,
        False otherwise (including on resolution errors).
    """
    try:
        resolved = pathlib.Path(file_path).resolve()
        root = pathlib.Path(root_dir).resolve()
        rel = resolved.relative_to(root).as_posix()
        return rel.startswith(".vault/") or rel == ".vault"
    except (ValueError, OSError):
        return False


def _make_sandbox_callback(mode: str, root_dir: str) -> Any:
    """Build a ``can_use_tool`` callback for the given agent mode.

    In ``read-write`` mode no restrictions are applied (returns ``None``).
    In ``read-only`` mode write operations are only allowed when the target
    path is inside ``.vault/``.

    Args:
        mode: Agent permission mode — ``"read-only"`` enforces sandbox
            restrictions; any other value disables them.
        root_dir: Project root directory passed to :func:`_is_vault_path`
            for path resolution.

    Returns:
        An async ``can_use_tool`` callback when ``mode`` is ``"read-only"``,
        or ``None`` when no restrictions should be applied.
    """
    if mode != "read-only":
        return None

    async def _callback(
        tool_name: str,
        tool_input: dict[str, Any],
        _context: ToolPermissionContext,
    ) -> PermissionResultAllow | PermissionResultDeny:
        """Evaluate whether a tool call should be permitted in read-only mode.

        Args:
            tool_name: Name of the tool being invoked (e.g. ``"Write"``,
                ``"Bash"``).
            tool_input: Raw input dict provided to the tool; ``"file_path"``
                is extracted for write-tool checks.
            _context: SDK permission context (unused).

        Returns:
            :class:`PermissionResultDeny` for shell tools or writes outside
            ``.vault/``; :class:`PermissionResultAllow` otherwise.
        """
        if tool_name in _SHELL_TOOLS:
            logger.warning(
                "Path access denied: %s (shell commands blocked)",
                tool_name,
            )
            return PermissionResultDeny(
                behavior="deny",
                message=(
                    "Read-only mode: shell commands are not permitted. "
                    "Use Read, Glob, or Grep tools instead."
                ),
                interrupt=False,
            )
        if tool_name in _WRITE_TOOLS:
            path = tool_input.get("file_path", "")
            if not _is_vault_path(path, root_dir):
                logger.warning(
                    "Path access denied: %s (write outside .vault/)",
                    path,
                )
                return PermissionResultDeny(
                    behavior="deny",
                    message=(
                        f"Read-only mode: writes are restricted to .vault/ "
                        f"(attempted: {path})"
                    ),
                    interrupt=False,
                )
        logger.debug("Path access allowed: %s", tool_name)
        return PermissionResultAllow(
            behavior="allow",
            updated_input=None,
            updated_permissions=None,
        )

    return _callback
