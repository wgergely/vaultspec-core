"""Shared ``--target`` option for all CLI commands.

Provides :data:`TargetOption`  - a reusable ``Annotated`` type alias that
adds ``--target / -t`` to any Typer command  - and :func:`apply_target`,
which initializes the workspace exactly once.

Priority for target resolution:
    subcommand ``--target`` > root ``-t`` > current working directory

The root callback (:func:`root.main`) stores the root-level target via
:func:`set_root_target` but does **not** resolve the workspace.  Each
subcommand calls :func:`apply_target` with its own ``--target`` value.
If the subcommand target is ``None``, the root target is used as
fallback.  If both are ``None``, the current working directory is used.
"""

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


def _resolve_framework_root(effective_target: Path | None) -> Path | None:
    """Return the CWD's ``.vaultspec/`` when ``--target`` points elsewhere.

    When the user specifies ``--target``, the *source of truth* for rules,
    skills, agents, and system prompts is the CWD workspace  - not the
    target directory.  The target is only the *destination* for synced
    artifacts and provider manifests.

    Returns ``None`` (let ``resolve_workspace`` use its default) when no
    ``--target`` is given, or when the CWD has no ``.vaultspec/``.
    """
    if effective_target is None:
        return None

    cwd = Path.cwd().resolve()
    resolved_target = effective_target.resolve()

    # If CWD *is* the target, no split needed  - single-workspace mode.
    try:
        if cwd == resolved_target or cwd.samefile(resolved_target):
            return None
    except (OSError, ValueError):
        pass

    cwd_fw = cwd / ".vaultspec"
    if cwd_fw.is_dir():
        return cwd_fw

    return None


def apply_target(target: Path | None, *, split_source: bool = False) -> None:
    """Initialize workspace from the effective target.

    Priority: *target* (subcommand) > :func:`set_root_target` > cwd.

    Args:
        target: Subcommand-level ``--target`` value (may be ``None``).
        split_source: When ``True`` **and** ``--target`` points to a
            different directory, the source content (``.vaultspec/rules/``)
            is read from the CWD workspace while the destination (tool
            directories, provider manifest) is at the target.  This is the
            correct model for ``sync``  - like ``rsync src/ dest/``.  Other
            commands (``spec add``, ``spec list``) operate on a single
            workspace, so they leave this ``False``.

    Idempotent  - if the workspace was already initialized with the same
    effective target, this is a no-op.

    Raises :class:`typer.Exit` on workspace resolution failure.
    """
    global _workspace_initialized

    effective = target or _root_target  # None means "use cwd" in resolve_workspace
    if _workspace_initialized and target is None:
        # Already initialized by a prior call (e.g. root-level target) and
        # no subcommand override  - skip redundant work.
        return

    from vaultspec_core.config.workspace import WorkspaceError, resolve_workspace
    from vaultspec_core.core.types import init_paths

    fw_root = _resolve_framework_root(effective) if split_source else None

    try:
        layout = resolve_workspace(target_override=effective, framework_root=fw_root)
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
    import dataclasses

    from vaultspec_core.core.types import WorkspaceContext, get_context, set_context

    effective = target or _root_target or Path.cwd()
    effective = effective.resolve()

    # Create or update the context with the resolved target_dir.
    # install/uninstall operate before full workspace resolution, so we
    # build a minimal context when none exists yet.
    try:
        ctx = get_context()
        set_context(dataclasses.replace(ctx, target_dir=effective))
    except LookupError:
        set_context(
            WorkspaceContext(
                root_dir=effective,
                target_dir=effective,
                rules_src_dir=effective,
                skills_src_dir=effective,
                agents_src_dir=effective,
                system_src_dir=effective,
                templates_dir=effective,
                hooks_dir=effective,
            )
        )
    return effective
