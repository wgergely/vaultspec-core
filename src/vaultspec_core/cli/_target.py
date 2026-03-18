"""Shared ``--target`` option for all CLI commands.

Provides :data:`TargetOption` — a reusable ``Annotated`` type alias that
adds ``--target / -t`` to any Typer command — and :func:`apply_target`,
which initializes the workspace exactly once.

Priority for target resolution:
    subcommand ``--target`` > root ``-t`` > current working directory

The root callback (:func:`root.main`) stores the root-level target via
:func:`set_root_target` but does **not** resolve the workspace.  Each
subcommand calls :func:`apply_target` with its own ``--target`` value.
If the subcommand target is ``None``, the root target is used as
fallback.  If both are ``None``, the current working directory is used.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_root_target: Path | None = None
_workspace_initialized: bool = False

# ---------------------------------------------------------------------------
# Reusable Annotated type alias
# ---------------------------------------------------------------------------

TargetOption = Annotated[
    Path | None,
    typer.Option(
        "--target",
        "-t",
        help="Target directory (defaults to current working directory).",
        dir_okay=True,
        file_okay=False,
        resolve_path=True,
    ),
]

# ---------------------------------------------------------------------------
# Root callback helpers
# ---------------------------------------------------------------------------


def set_root_target(target: Path | None) -> None:
    """Store the root-level ``-t`` / ``--target`` value (no init yet)."""
    global _root_target
    _root_target = target


def reset() -> None:
    """Reset module state (for test isolation)."""
    global _root_target, _workspace_initialized
    _root_target = None
    _workspace_initialized = False


# ---------------------------------------------------------------------------
# Subcommand initialization
# ---------------------------------------------------------------------------


def apply_target(target: Path | None) -> None:
    """Initialize workspace from the effective target.

    Priority: *target* (subcommand) > :func:`set_root_target` > cwd.

    Idempotent — if the workspace was already initialized with the same
    effective target, this is a no-op.

    Raises :class:`typer.Exit` on workspace resolution failure.
    """
    global _workspace_initialized

    effective = target or _root_target  # None means "use cwd" in resolve_workspace
    if _workspace_initialized and target is None:
        # Already initialized by a prior call (e.g. root-level target) and
        # no subcommand override — skip redundant work.
        return

    from vaultspec_core.config.workspace import WorkspaceError, resolve_workspace
    from vaultspec_core.core.types import init_paths

    try:
        layout = resolve_workspace(target_override=effective)
        init_paths(layout)
        _workspace_initialized = True
    except WorkspaceError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


def apply_target_install(target: Path | None) -> Path:
    """Resolve target for install / uninstall (no workspace resolution).

    Priority: *target* (subcommand) > :func:`set_root_target` > cwd.

    Returns the resolved target path.
    """
    from vaultspec_core.core import types as _t

    effective = target or _root_target or Path.cwd()
    effective = effective.resolve()
    _t.TARGET_DIR = effective
    return effective
