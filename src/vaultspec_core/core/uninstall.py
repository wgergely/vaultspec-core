"""Remove the vaultspec framework and its provider artifacts from a project.

Covers both the "remove everything" and "remove one provider" shapes of
uninstall, including the shared managed-directory/file deletion primitives
and the post-removal gitignore/gitattributes reconciliation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import types as _t
from .enums import ManagedState, ProviderCapability, Tool
from .exceptions import ProviderError
from .git_artifacts import block_management_enabled
from .gitattributes import ensure_gitattributes_block
from .gitignore import (
    collect_provider_artifacts,
    ensure_gitignore_block,
    get_recommended_entries,
    prune_orphaned_lock_sentinels,
)
from .helpers import rmtree_robust
from .manifest import (
    ManifestData,
    manifest_lock,
    providers_sharing_dir,
    providers_sharing_file,
    read_manifest_data,
    remove_provider,
    write_manifest_data,
)
from .precommit import ALL_MANAGED_HOOK_IDS, strip_managed_precommit_hooks
from .provider_registry import (
    PROVIDER_TO_TOOLS,
    filter_tools,
    rel,
    validate_provider,
    validate_skip,
)
from .provision import ensure_tool_configs

logger = logging.getLogger(__name__)

__all__ = [
    "uninstall_run",
]

# Map directory names → component owners (for skip filtering).
# .agents/ is shared by antigravity, gemini, and codex (all place skills there
# via init_paths), so it must be preserved when any of its owners is skipped.
_UNINSTALL_DIR_OWNERS: dict[str, list[str]] = {
    ".vaultspec": ["core"],
    ".vault": ["vault"],
    ".claude": ["claude"],
    ".gemini": ["gemini"],
    ".agents": ["antigravity", "gemini", "codex"],
    ".codex": ["codex"],
}
_UNINSTALL_DIR_LABELS: dict[str, str] = {
    ".vaultspec": "core",
    ".vault": "vault",
    ".claude": "claude",
    ".gemini": "gemini",
    ".agents": "antigravity",
    ".codex": "codex",
}
_UNINSTALL_FILE_LABELS: dict[str, str] = {
    "CLAUDE.md": "claude (config)",
    "GEMINI.md": "gemini (config)",
    "AGENTS.md": "codex (config)",
    ".mcp.json": "mcp",
}
# Map file names → owning components (for skip filtering).
# GEMINI.md is shared by gemini and antigravity (both set it as their
# `config_file` in `types.py`), so it must be preserved when any of its
# owners is skipped - mirroring `_UNINSTALL_DIR_OWNERS` above.
_UNINSTALL_FILE_OWNERS: dict[str, list[str]] = {
    "CLAUDE.md": ["claude"],
    "GEMINI.md": ["gemini", "antigravity"],
    "AGENTS.md": ["codex"],
}


def _delete_managed_dir(
    root: Path, directory: Path, *, dry_run: bool, errors: list[str]
) -> bool:
    """Delete *directory*, or preview the deletion under *dry_run*.

    Returns:
        ``True`` when the removal succeeded (or was previewed) and the caller
        should record it, ``False`` when it failed and was reported in *errors*.
    """
    if dry_run:
        return True
    try:
        rmtree_robust(directory)
    except OSError as exc:
        errors.append(f"Failed to remove {rel(root, directory)}: {exc}")
        return False
    return True


def _delete_managed_file(
    root: Path, file: Path, *, dry_run: bool, errors: list[str]
) -> bool:
    """Delete *file*, or preview the deletion under *dry_run*.

    Returns:
        ``True`` when the removal succeeded (or was previewed) and the caller
        should record it, ``False`` when it failed and was reported in *errors*.
    """
    if dry_run:
        return True
    try:
        file.unlink()
    except OSError as exc:
        errors.append(f"Failed to remove {rel(root, file)}: {exc}")
        return False
    return True


def _uninstall_mcp_targets(
    root: Path,
    *,
    enrolled: tuple[Tool, ...],
    provider: Tool | str = "all",
    dry_run: bool,
    removed: list[tuple[str, str]],
    errors: list[str],
) -> None:
    """Retire vaultspec's native MCP enrollment from the *enrolled* hosts.

    Appends every reconciled target to *removed* and any host-level failure to
    *errors*.
    """
    from .mcps import mcp_uninstall, resolve_mcp_targets

    uninstalled = mcp_uninstall(
        root,
        dry_run=dry_run,
        provider=provider,
        enrolled=enrolled,
    )
    errors.extend(uninstalled.errors)
    for target in resolve_mcp_targets(
        provider=provider,
        target_dir=root,
        enrolled=enrolled,
    ):
        target_result = uninstalled.per_tool.get(target.provider.value)
        if target_result and target_result.items:
            removed.append((rel(root, target.path), "mcp"))


def _uninstall_precommit_hooks(
    root: Path, *, dry_run: bool, removed: list[tuple[str, str]]
) -> None:
    """Strip vaultspec-managed hooks from a legacy ``.pre-commit-config.yaml``.

    This deliberately runs even when ``prek.toml`` owns the hook boundary
    (:func:`collect_prek_boundary`): install and sync refuse to write the YAML
    under prek, but uninstall stripping vaultspec hooks from a legacy YAML is
    residue removal - leave-no-trace semantics - not management of the file.
    """
    from ruamel.yaml import YAMLError

    precommit_path = root / ".pre-commit-config.yaml"
    if not precommit_path.exists():
        return

    if dry_run:
        try:
            raw = precommit_path.read_text(encoding="utf-8")
        except OSError:
            return
        if any(f"id: {hid}" in raw for hid in ALL_MANAGED_HOOK_IDS):
            removed.append((rel(root, precommit_path), "precommit"))
        return

    if not strip_managed_precommit_hooks(precommit_path):
        return
    removed.append((rel(root, precommit_path), "precommit"))
    try:
        # Read-modify-write, so the whole cycle holds the manifest lock:
        # `write_manifest_data` takes none of its own (issue #418).
        with manifest_lock(root):
            mdata = read_manifest_data(root)
            if mdata.precommit_managed:
                mdata.precommit_managed = False
                write_manifest_data(root, mdata)
    # UnicodeDecodeError subclasses ValueError, not OSError, so a file that
    # exists and cannot be decoded escaped this net and surfaced as a raw
    # traceback (issue #407).
    except (YAMLError, OSError, UnicodeDecodeError):
        pass


def _uninstall_everything(
    root: Path,
    *,
    skip: set[str],
    keep_vault: bool,
    dry_run: bool,
    removed: list[tuple[str, str]],
    errors: list[str],
) -> None:
    """Remove every managed directory, config file, and hook block under *root*.

    Honours *skip* per component and appends what was removed to *removed*.
    """
    # .vaultspec is deleted LAST so the manifest survives partial failures.
    managed_dirs = [
        root / ".claude",
        root / ".gemini",
        root / ".agents",
        root / ".codex",
    ]
    if not keep_vault:
        managed_dirs.append(root / ".vault")
    managed_dirs.append(root / ".vaultspec")

    # Reconcile native MCP targets before provider directories and
    # ownership state are removed.
    if "mcp" not in skip:
        active_ctx = _t.get_context()
        _uninstall_mcp_targets(
            root,
            enrolled=tuple(
                tool
                for tool, config in active_ctx.tool_configs.items()
                if ProviderCapability.MCPS in config.capabilities
                and tool.value not in skip
            ),
            dry_run=dry_run,
            removed=removed,
            errors=errors,
        )

    for directory in managed_dirs:
        skipped = [
            owner
            for owner in _UNINSTALL_DIR_OWNERS.get(directory.name, [])
            if owner in skip
        ]
        if skipped:
            logger.info("Skipping %s (--skip %s)", directory.name, ", ".join(skipped))
            continue
        if not directory.exists():
            continue
        if _delete_managed_dir(root, directory, dry_run=dry_run, errors=errors):
            label = _UNINSTALL_DIR_LABELS.get(directory.name, "")
            removed.append((str(directory).replace("\\", "/") + "/", label))

    for file in (root / "CLAUDE.md", root / "GEMINI.md", root / "AGENTS.md"):
        skipped = [
            owner
            for owner in _UNINSTALL_FILE_OWNERS.get(file.name, [])
            if owner in skip
        ]
        if skipped:
            logger.info("Skipping %s (--skip %s)", file.name, ", ".join(skipped))
            continue
        if not file.exists():
            continue
        if _delete_managed_file(root, file, dry_run=dry_run, errors=errors):
            label = _UNINSTALL_FILE_LABELS.get(file.name, "")
            removed.append((str(file).replace("\\", "/"), label))

    if "precommit" not in skip:
        _uninstall_precommit_hooks(root, dry_run=dry_run, removed=removed)


def _uninstall_provider_artifacts(
    root: Path,
    provider: str,
    *,
    skip: set[str],
    dry_run: bool,
    removed: list[tuple[str, str]],
    errors: list[str],
) -> None:
    """Remove one provider's artifacts, preserving directories still shared.

    Directories and files another installed provider still owns are logged and
    left in place; the manifest is updated once every tool is off disk.
    """
    tools = filter_tools(PROVIDER_TO_TOOLS.get(provider, []), skip)

    if "mcp" not in skip:
        active_ctx = _t.get_context()
        mcp_tools = tuple(
            tool
            for tool in tools
            if ProviderCapability.MCPS in active_ctx.tool_configs[tool].capabilities
        )
        if mcp_tools:
            _uninstall_mcp_targets(
                root,
                enrolled=mcp_tools,
                provider=provider,
                dry_run=dry_run,
                removed=removed,
                errors=errors,
            )

    for tool in tools:
        dirs, files = collect_provider_artifacts(root, tool)

        for directory in dirs:
            if not directory.exists():
                continue
            sharing = providers_sharing_dir(root, directory, exclude=provider)
            if sharing:
                logger.info(
                    "Preserving %s (still used by: %s)",
                    directory.relative_to(root),
                    ", ".join(sorted(sharing)),
                )
                continue
            if _delete_managed_dir(root, directory, dry_run=dry_run, errors=errors):
                removed.append((str(directory).replace("\\", "/") + "/", tool.value))

        for file in files:
            if not file.exists():
                continue
            sharing = providers_sharing_file(root, file, exclude=provider)
            if sharing:
                logger.info(
                    "Preserving %s (still used by: %s)",
                    file.relative_to(root),
                    ", ".join(sorted(sharing)),
                )
                continue
            if _delete_managed_file(root, file, dry_run=dry_run, errors=errors):
                removed.append((str(file).replace("\\", "/"), f"{tool.value} (config)"))

    # Update manifest once after all tools are removed from disk
    if not dry_run:
        for tool in tools:
            remove_provider(root, tool.value)


def _reconcile_uninstall_git_blocks(
    root: Path, *, keep_vault: bool, was_gitignore_managed: bool
) -> None:
    """Re-sync the managed gitignore and gitattributes blocks after removal."""
    try:
        mdata_after = read_manifest_data(root)
    except Exception:
        mdata_after = ManifestData()

    recommended = get_recommended_entries(root)
    # If no providers remain and we are not keeping the vault, remove the block.
    # Otherwise, we sync it if it was managed before.
    if not mdata_after.installed and not keep_vault:
        ensure_gitignore_block(root, [], state=ManagedState.ABSENT)
        ensure_gitattributes_block(root, state=ManagedState.ABSENT)
    elif (
        recommended
        and was_gitignore_managed
        and block_management_enabled(root, "gitignore")
        # Uninstall removes; it does not provision. `ensure_gitignore_block`
        # creates an absent file now, so without this gate a partial uninstall
        # would write back a `.gitignore` the workspace had deleted - and do it
        # before any sync could read that deletion as the opt-out gesture.
        and (root / ".gitignore").is_file()
    ):
        ensure_gitignore_block(root, recommended, state=ManagedState.PRESENT)

    # Reconcile `.gitattributes` on the same terms as its twin rather than
    # only in the full-removal case above. A partial uninstall used to leave
    # it at whatever the last install wrote and never look at it again, so it
    # was the one managed file this path did not keep in step (issue #409).
    # As with `.gitignore`, an absent file is not created here: uninstall
    # removes, it does not provision.
    if (
        (mdata_after.installed or keep_vault)
        and block_management_enabled(root, "gitattributes")
        and (root / ".gitattributes").is_file()
    ):
        ensure_gitattributes_block(root, state=ManagedState.PRESENT)

    # Prune sentinels whose subject this uninstall just removed. This has to
    # run after the block writes above, not before: `advisory_lock` creates a
    # sentinel as a side effect of the very write that reconciles the block,
    # so pruning first would delete one and then immediately recreate it.
    for orphan in prune_orphaned_lock_sentinels(root):
        logger.info("Removed orphaned lock sentinel %s", orphan)


def uninstall_run(
    path: Path,
    provider: str = "all",
    keep_vault: bool = False,
    dry_run: bool = False,
    force: bool = False,
    skip: set[str] | None = None,
) -> dict[str, Any]:
    """Remove the vaultspec framework from a project directory.

    Args:
        path: Target directory.
        provider: Provider to uninstall (``all``, ``core``, ``<provider>``).
        keep_vault: Preserve ``.vault/`` documentation directory.
        dry_run: Preview what would be removed without deleting.
        force: Required to execute. Uninstall is destructive.
        skip: Set of component names to skip (``core`` and/or provider names).

    Returns:
        A dict describing the result:
        - ``"action"``: ``"dry_run"`` or ``"uninstall"``
        - ``"removed"``: list of ``(path, label)`` tuples

    Raises:
        ProviderError: If *provider* is invalid or *force* not set.
    """
    validate_provider(provider)
    skip = validate_skip(skip)

    # Safety gate: require --force for destructive operations
    if not force and not dry_run:
        raise ProviderError(
            "Uninstall is destructive. Pass --force to confirm, "
            "or use --dry-run to preview."
        )

    # Bootstrap a minimal context so ensure_tool_configs can proceed
    _t.set_context(
        _t.WorkspaceContext(
            root_dir=path,
            target_dir=path,
            rules_src_dir=path,
            skills_src_dir=path,
            agents_src_dir=path,
            system_src_dir=path,
            templates_dir=path,
            hooks_dir=path,
        )
    )
    ensure_tool_configs(path)

    # Uninstalling "core" cascades to all providers
    effective_provider = "all" if provider == "core" else provider

    removed: list[tuple[str, str]] = []  # (path, label)
    errors: list[str] = []

    # Capture manifest state before potential destruction
    try:
        mdata_before = read_manifest_data(path)
    except Exception:
        # Fallback if manifest is already gone or corrupted
        mdata_before = ManifestData()

    if effective_provider == "all":
        _uninstall_everything(
            path,
            skip=skip,
            keep_vault=keep_vault,
            dry_run=dry_run,
            removed=removed,
            errors=errors,
        )
    else:
        _uninstall_provider_artifacts(
            path,
            effective_provider,
            skip=skip,
            dry_run=dry_run,
            removed=removed,
            errors=errors,
        )

    # Re-sync gitignore and gitattributes blocks
    if not dry_run:
        _reconcile_uninstall_git_blocks(
            path,
            keep_vault=keep_vault,
            was_gitignore_managed=mdata_before.gitignore_managed,
        )

    action = "dry_run" if dry_run else "uninstall"
    result: dict[str, Any] = {
        "action": action,
        "removed": removed,
        "keep_vault": keep_vault,
        "path": path,
    }
    if errors:
        result["errors"] = errors
    return result
