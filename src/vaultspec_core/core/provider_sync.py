"""Reconcile enrolled providers and workspace-level state with the source corpus.

Implements ``sync_provider`` (the ``vaultspec-core sync`` backend): running
every resource sync pass for one or all providers, backfilling missing
structural directories, and reconciling the pre-commit, gitignore, and
gitattributes management state that rides along with a sync.
"""

from __future__ import annotations

import contextvars
import logging
from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path

from . import types as _t
from .enums import ProviderCapability, Tool
from .exceptions import (
    ProviderError,
    ProviderNotInstalledError,
    WorkspaceNotInitializedError,
)
from .git_artifacts import block_management_enabled, managed_block_presence
from .gitattributes import ensure_gitattributes_block
from .gitignore import (
    ensure_gitignore_block,
    get_recommended_entries,
    prune_orphaned_lock_sentinels,
)
from .helpers import ensure_dir
from .install_mode import stamp_manifest_version_no_downgrade
from .manifest import (
    manifest_lock,
    read_manifest,
    read_manifest_data,
    write_manifest_data,
)
from .precommit import scaffold_precommit
from .provider_registry import SYNC_PROVIDERS, rel, validate_skip

logger = logging.getLogger(__name__)

__all__ = [
    "sync_provider",
]

# Single-provider sync targets mapped to the tool they narrow the context to.
_SYNC_PROVIDER_TOOLS: dict[str, Tool] = {
    "claude": Tool.CLAUDE,
    "gemini": Tool.GEMINI,
    "antigravity": Tool.ANTIGRAVITY,
    "codex": Tool.CODEX,
}


def _empty_sync_results() -> list[_t.SyncResult]:
    """Return the positional no-op result set for a fully skipped sync."""
    return [_t.SyncResult() for _ in range(5)]


def _backfill_structures(*, skip: set[str], dry_run: bool) -> _t.SyncResult:
    """Create missing structural provider directories during sync (#133).

    Content files are backfilled by the per-resource sync passes (their
    ``apply_file_sync`` adds any missing destination), but a content-less
    structural directory such as a provider's ``workflows/`` is only ever
    created by ``install``/``scaffold_provider``. After an upgrade that
    introduces such a directory, ``sync`` left the provider ``partial``
    while reporting success ("will be addressed by sync") - a no-op. This
    backfill makes that promise real: it creates only directories that are
    missing, never overwriting existing content, so it is safe at every
    ``--force`` level and previews correctly under ``--dry-run``.
    """
    result = _t.SyncResult()
    active_ctx = _t.get_context()
    target = active_ctx.target_dir
    installed = read_manifest_data(target).installed
    for tool, cfg in active_ctx.tool_configs.items():
        # Only backfill providers the operator actually enrolled; never
        # materialise a provider directory a core-only or partial install
        # deliberately omitted.
        if tool.value in skip or tool.value not in installed:
            continue
        caps = cfg.capabilities
        structural: list[Path] = []
        if ProviderCapability.RULES in caps and cfg.rules_dir:
            structural.append(cfg.rules_dir)
        if ProviderCapability.SKILLS in caps and cfg.skills_dir:
            structural.append(cfg.skills_dir)
        if ProviderCapability.AGENTS in caps and cfg.agents_dir:
            structural.append(cfg.agents_dir)
        if ProviderCapability.WORKFLOWS in caps and cfg.workflows_dir:
            structural.append(cfg.workflows_dir)
        for directory in structural:
            if directory.exists():
                continue
            result.items.append((rel(target, directory).replace("\\", "/"), "[ADD]"))
            result.added += 1
            if not dry_run:
                ensure_dir(directory)
    return result


def _mcp_sync_pass(
    *,
    skip: set[str],
    dry_run: bool,
    force: bool,
    mcp_provider: Tool | str,
) -> tuple[Callable[[], _t.SyncResult], str]:
    """Build the MCP reconciliation pass for :func:`_run_all_syncs`."""
    from .mcps import mcp_sync as _mcp_sync

    active_ctx = _t.get_context()
    installed = read_manifest(active_ctx.target_dir)
    enrolled = tuple(
        tool
        for tool in active_ctx.tool_configs
        if tool.value in installed and tool.value not in skip
    )
    return (
        lambda: _mcp_sync(
            dry_run=dry_run,
            force=force,
            prune=force,
            provider=mcp_provider,
            target_dir=active_ctx.target_dir,
            enrolled=enrolled,
        ),
        "mcps",
    )


def _run_all_syncs(
    *,
    skip: set[str],
    dry_run: bool,
    force: bool,
    include_mcp: bool = True,
    mcp_provider: Tool | str = "all",
) -> list[_t.SyncResult]:
    """Run every resource sync pass, isolating each pass's failure.

    A pass that raises is reported as an error-carrying :class:`SyncResult` in
    its positional slot so the remaining passes still run.
    """
    from .agents import agents_sync
    from .config_gen import config_sync
    from .rules import rules_sync
    from .skills import skills_sync
    from .system import system_sync

    results: list[_t.SyncResult] = []
    sync_passes: list[tuple[Callable[[], _t.SyncResult], str]] = [
        (lambda: rules_sync(prune=force, dry_run=dry_run), "rules"),
        (lambda: skills_sync(prune=force, dry_run=dry_run), "skills"),
        (lambda: agents_sync(prune=force, dry_run=dry_run), "agents"),
        (lambda: system_sync(dry_run=dry_run, force=force), "system"),
        (lambda: config_sync(dry_run=dry_run, force=force), "config"),
    ]
    if include_mcp and "mcp" not in skip:
        sync_passes.append(
            _mcp_sync_pass(
                skip=skip,
                dry_run=dry_run,
                force=force,
                mcp_provider=mcp_provider,
            )
        )
    if "hooks" not in skip:
        from .provider_hooks import provider_hooks_sync

        sync_passes.append((lambda: provider_hooks_sync(dry_run=dry_run), "hooks"))
    for sync_fn, label in sync_passes:
        try:
            results.append(sync_fn())
        except Exception as exc:
            logger.error("Sync pass '%s' failed: %s", label, exc)
            error_result = _t.SyncResult()
            error_result.errors.append(f"{label} sync failed: {exc}")
            results.append(error_result)
    # Structural backfill runs last and is appended after the positional
    # resource passes; renderers treat any result beyond the known pass
    # labels as structural (issue #133).
    results.append(_backfill_structures(skip=skip, dry_run=dry_run))
    return results


def _reconcile_precommit_management(target_dir: Path) -> None:
    """Re-scaffold managed pre-commit hooks, or stand down if the user removed them."""
    mdata = read_manifest_data(target_dir)
    if not mdata.precommit_managed:
        return

    from .diagnosis.collectors import collect_precommit_state
    from .diagnosis.signals import PrecommitSignal

    signal = collect_precommit_state(target_dir)
    if signal in (PrecommitSignal.NO_HOOKS, PrecommitSignal.NO_FILE):
        mdata.precommit_managed = False
        write_manifest_data(target_dir, mdata)
        logger.info("Pre-commit hooks removed by user, disabling management")
        return
    scaffold_precommit(target_dir)


def _reconcile_gitignore_opt_out(target_dir: Path) -> None:
    """Re-sync the managed ``.gitignore`` block, honouring a user opt-out.

    Checks whether the user removed the managed block BEFORE re-creating it.
    If the block is gone but the manifest still says ``managed=True``, the user
    opted out -- honour that by flipping the flag and recording the opt-out.

    The opt-out is recorded explicitly rather than inferred from
    ``gitignore_managed`` being ``False``, which also describes a workspace
    where management was never established. Upgrades re-establish the second
    and must leave the first alone.

    Only a file that was read and found free of markers counts as the gesture.
    A file that could not be read answers nothing, and recording a decision on
    the strength of it would turn an unreadable file into a durable opt-out
    that only ``--force`` undoes - and would restore the benign diagnosis this
    workspace was just taught to withhold.
    """
    gi_path = target_dir / ".gitignore"
    if not block_management_enabled(target_dir, "gitignore"):
        return
    mdata = read_manifest_data(target_dir)
    if not mdata.gitignore_managed:
        return

    presence = managed_block_presence(gi_path)
    if presence is None:
        logger.warning(
            "Cannot read %s; leaving gitignore management as it stands", gi_path
        )
        return
    if presence:
        ensure_gitignore_block(target_dir, get_recommended_entries(target_dir))
        return

    # The per-machine echo only. Writing the committed declaration here would
    # let an inference about intent modify a file the whole team shares, which
    # is what `spec gitignore disable` exists to do explicitly.
    logger.info(
        "Managed block absent from %s; this machine will stop managing it. "
        "Run 'vaultspec-core spec gitignore disable' to record that for the "
        "whole project, or 'vaultspec-core install --force' to resume.",
        gi_path,
    )
    # Re-read under the lock rather than reusing the copy above: this is a
    # read-modify-write, and `write_manifest_data` takes no lock of its own -
    # its own docstring says the caller must hold one across the whole cycle
    # (issue #418). The lock is scoped to the mutation so it never nests with
    # the `.gitignore` lock the block writer takes on the branch above.
    with manifest_lock(target_dir):
        mdata = read_manifest_data(target_dir)
        mdata.gitignore_managed = False
        mdata.gitignore_opted_out = True
        write_manifest_data(target_dir, mdata)


def _reconcile_gitattributes_opt_out(target_dir: Path) -> None:
    """Re-sync the managed ``.gitattributes`` block (same pattern as gitignore)."""
    ga_path = target_dir / ".gitattributes"
    if not block_management_enabled(target_dir, "gitattributes"):
        return
    mdata = read_manifest_data(target_dir)
    if not mdata.gitattributes_managed:
        return

    presence = managed_block_presence(ga_path)
    if presence is None:
        logger.warning(
            "Cannot read %s; leaving gitattributes management as it stands", ga_path
        )
        return
    if presence:
        ensure_gitattributes_block(target_dir)
        return

    logger.info(
        "Managed block absent from %s; this machine will stop managing it. "
        "Run 'vaultspec-core spec gitattributes disable' to record that for "
        "the whole project, or 'vaultspec-core install --force' to resume.",
        ga_path,
    )
    # Same cycle, same reason as its twin above (issue #418).
    with manifest_lock(target_dir):
        mdata = read_manifest_data(target_dir)
        mdata.gitattributes_managed = False
        mdata.gitattributes_opted_out = True
        write_manifest_data(target_dir, mdata)


def _stamp_last_synced(target_dir: Path, candidates: Iterable[str]) -> None:
    """Record a ``last_synced`` timestamp for every installed name in *candidates*."""
    import datetime

    now = datetime.datetime.now(tz=datetime.UTC).isoformat()
    # Read-modify-write, so the whole cycle holds the lock (issue #418).
    with manifest_lock(target_dir):
        mdata = read_manifest_data(target_dir)
        for name in candidates:
            if name not in mdata.installed:
                continue
            mdata.provider_state.setdefault(name, {})
            mdata.provider_state[name]["last_synced"] = now
        stamp_manifest_version_no_downgrade(mdata)
        write_manifest_data(target_dir, mdata)


def _target_hooks_dir(target_dir: Path) -> Path:
    """Return *target_dir*'s own ``.vaultspec/hooks`` directory.

    ``sync --target`` reads its source content (rules, skills, agents) from
    the CWD workspace while writing to *target_dir* - the correct model for
    a sync (see :func:`~vaultspec_core.cli._target.apply_target`'s
    ``split_source``). Hooks are different: they react to an event that just
    happened *to* a workspace, so the ``config.synced`` hook fired after a
    sync must come from the workspace that was actually synced, not from
    whichever workspace happens to be the ambient CWD - otherwise a
    ``--target`` sync executes another workspace's hook definitions against
    the target, which is surprising at best and widens the blast radius of
    hook execution at worst.

    Resolved independently of the ambient context (rather than read off
    ``get_context()``) so this is correct even when the ambient context is
    mid-sync and reflects the CWD/source split.

    Falls back to the ambient context's ``hooks_dir`` if resolution fails
    for any reason: ``fire_hooks`` itself is a best-effort, silently-caught
    side effect of a sync (see its docstring), and a hooks-directory
    resolution problem must degrade the same way rather than fail a sync
    that otherwise completed.
    """
    from ..config import resolve_workspace

    try:
        return resolve_workspace(target_override=target_dir).vaultspec_dir / "hooks"
    except Exception:
        logger.warning(
            "Could not resolve %s's own hooks directory; falling back to the "
            "ambient workspace context",
            target_dir,
            exc_info=True,
        )
        return _t.get_context().hooks_dir


def _sync_all_providers(
    ctx: _t.WorkspaceContext,
    *,
    skip: set[str],
    dry_run: bool,
    force: bool,
) -> list[_t.SyncResult]:
    """Sync every enrolled provider, then reconcile workspace-level state."""

    def _sync_all_with_configs(
        narrowed_configs: dict[Tool, _t.ToolConfig] | None,
    ) -> list[_t.SyncResult]:
        if narrowed_configs is not None:
            _t.set_context(replace(ctx, tool_configs=narrowed_configs))
        logger.info("Syncing all resources...")
        results = _run_all_syncs(skip=skip, dry_run=dry_run, force=force)
        if not dry_run:
            from vaultspec_core.hooks import fire_hooks

            fire_hooks(
                "config.synced",
                {"root": str(ctx.target_dir), "event": "config.synced"},
                hooks_dir=_target_hooks_dir(ctx.target_dir),
            )
            logger.info("Done.")
        return results

    # When skipping providers, narrow tool_configs in a copied context
    skipped_tools = {Tool(name) for name in skip if name in {t.value for t in Tool}}
    narrowed_configs: dict[Tool, _t.ToolConfig] | None = None
    if skipped_tools:
        narrowed_configs = {
            k: v for k, v in ctx.tool_configs.items() if k not in skipped_tools
        }

    copied = contextvars.copy_context()
    results = copied.run(_sync_all_with_configs, narrowed_configs)

    if dry_run:
        return results

    if "precommit" not in skip:
        _reconcile_precommit_management(ctx.target_dir)

    for orphan in prune_orphaned_lock_sentinels(ctx.target_dir):
        logger.info("Removed orphaned lock sentinel %s", orphan)

    _reconcile_gitignore_opt_out(ctx.target_dir)
    _reconcile_gitattributes_opt_out(ctx.target_dir)

    # Update last_synced timestamps for installed providers only
    _stamp_last_synced(
        ctx.target_dir,
        [tool.value for tool in ctx.tool_configs if tool.value not in skip],
    )
    return results


def sync_provider(
    provider: str,
    *,
    dry_run: bool = False,
    force: bool = False,
    skip: set[str] | None = None,
) -> list[_t.SyncResult]:
    """Sync resources for a single provider target.

    ``provider`` must be one of :data:`SYNC_PROVIDERS`.  The special value
    ``"all"`` syncs every provider and fires post-sync hooks.

    When *force* is ``True``, stale destination files are pruned and
    user-authored system/config files are overwritten.  When ``False``
    (the default), the sync is additive-only and any divergences are
    reported as warnings on the returned :class:`SyncResult` objects.

    Args:
        provider: Provider target to sync.
        dry_run: Preview changes without writing.
        force: Prune stale files and overwrite user-authored content.
        skip: Set of provider names to exclude from the sync.

    Returns:
        A list of :class:`SyncResult` objects from each sync pass.

    Raises:
        ProviderError: If *provider* is invalid.
        WorkspaceNotInitializedError: If ``.vaultspec/`` does not exist.
        ProviderNotInstalledError: If the specified provider is not installed.
    """
    if provider not in SYNC_PROVIDERS:
        raise ProviderError(
            f"Unknown sync target '{provider}'. "
            f"Valid: {', '.join(sorted(SYNC_PROVIDERS))}"
        )

    skip = validate_skip(skip, allow_core=False)

    ctx = _t.get_context()

    # Guard: refuse to sync if vaultspec isn't installed at the target
    if not (ctx.target_dir / ".vaultspec").exists():
        raise WorkspaceNotInitializedError(
            f"No .vaultspec/ found at {ctx.target_dir}.",
            hint=f"Run 'vaultspec-core install {ctx.target_dir}' first.",
        )

    if provider == "all":
        return _sync_all_providers(ctx, skip=skip, dry_run=dry_run, force=force)

    # Validate provider is installed unless the provider was explicitly skipped.
    installed = read_manifest(ctx.target_dir)
    if provider in skip:
        return _empty_sync_results()
    if installed and provider not in installed:
        raise ProviderNotInstalledError(
            f"Provider '{provider}' is not installed.",
            hint=(
                f"Run 'vaultspec-core install "
                f"--target {ctx.target_dir} {provider}' first."
            ),
        )

    # Per-provider sync: filter tool_configs to only the requested tool.
    tool = _SYNC_PROVIDER_TOOLS.get(provider)
    requested: set[Tool] = {tool} if tool is not None else set()

    def _sync_single_provider(
        provider_configs: dict[Tool, _t.ToolConfig],
    ) -> list[_t.SyncResult]:
        _t.set_context(replace(ctx, tool_configs=provider_configs))
        logger.info("Syncing provider: %s ...", provider)
        include_mcp = any(
            ProviderCapability.MCPS in config.capabilities
            for config in provider_configs.values()
        )
        results = _run_all_syncs(
            skip=skip,
            dry_run=dry_run,
            force=force,
            include_mcp=include_mcp,
            mcp_provider=provider,
        )
        if not dry_run:
            logger.info("Done.")
        return results

    narrowed = {k: v for k, v in ctx.tool_configs.items() if k in requested}
    copied = contextvars.copy_context()
    results = copied.run(_sync_single_provider, narrowed)

    if not dry_run:
        # The managed git blocks are repository-level, not per-provider: a
        # workspace that deleted one has declined it whichever provider the
        # reader happened to name. Only the "all" path used to reconcile them,
        # so `sync claude` left the opt-out unrecorded - and once the diagnosis
        # weighs an unrecorded absence, that is a warning the reader cannot
        # clear without knowing which spelling of sync clears it.
        _reconcile_gitignore_opt_out(ctx.target_dir)
        _reconcile_gitattributes_opt_out(ctx.target_dir)
        _stamp_last_synced(ctx.target_dir, [tool_type.value for tool_type in requested])

    return results
