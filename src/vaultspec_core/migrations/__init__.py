"""Versioned migration registry for vaultspec-managed workspaces.

Schema migrations relocate or rewrite workspace content - ``.vault/``
documents or the ``.vaultspec/`` framework tree - when a new release of
vaultspec-core changes the on-disk shape. Each migration
declares its target release version and exposes an idempotent
``migrate(workspace) -> MigrationResult`` callable. The driver
:func:`run_pending_migrations` reads the workspace manifest, runs every
entry whose ``target_version`` exceeds the manifest's
``vaultspec_version``, then bumps the manifest version on success.

Triggers:

- :func:`vaultspec_core.core.commands.install_run` runs the driver in
  the upgrade branch so explicit upgrades migrate immediately.
- :func:`vaultspec_core.cli._migration_hook.ensure_migrated` runs the
  driver from the two layout-sensitive authoring verbs
  (``vaultspec-core vault add`` and ``vaultspec-core vault feature index``),
  which write a document to a location the schema decides.
- :func:`vaultspec_core.vaultcore.repair.repair_vault` runs the driver
  from its preflight.
- The ``vaultspec-core migrations`` CLI subcommand exposes
  ``status`` and ``run`` for explicit operator control.

Nothing else triggers the driver. In particular no *read* does:
scanning, graph construction, ``vault list``, ``vault check`` without
``--fix``, the metrics pass, and every MCP query run against an
unmigrated workspace observe the layout they find and leave it alone.
The driver's entries delete and relocate tracked user documents, and a
caller that only asked to read has not authorised that (issue #443).
Reads instead surface the drift through :func:`warn_if_pending`.

A migration whose body raises bubbles the exception up and prevents
the manifest version bump. The next invocation re-attempts from the
same starting version, so partial failures do not leave the workspace
half-migrated from the registry's bookkeeping perspective.

See also:
    :class:`vaultspec_core.core.manifest.ManifestData` for the
    ``vaultspec_version`` field that anchors the comparison.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from ..core.helpers import advisory_lock, package_version, parse_version_tuple
from ..core.manifest import (
    MANIFEST_FILENAME,
    ManifestData,
    read_manifest_data,
    write_manifest_data,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

__all__ = [
    "MIGRATION_LOGGER",
    "REGISTRY",
    "Migration",
    "MigrationError",
    "MigrationResult",
    "MigrationStatus",
    "list_pending",
    "migration_status",
    "reset_workspace_cache",
    "run_pending_migrations",
    "warn_if_pending",
]


class MigrationError(RuntimeError):
    """Raised by a migration when a non-recoverable failure prevents progress.

    The driver does not catch this; the exception propagates to the
    caller so the manifest version bump is suppressed and the next
    invocation re-attempts from the same starting version. Migration
    bodies should reserve this for real I/O or data-safety failures,
    not recoverable drift in generated artifacts.
    """


MIGRATION_LOGGER = "vaultspec_core.migrations"
logger = logging.getLogger(MIGRATION_LOGGER)


def _invalidate_graph_cache(workspace: Path) -> None:
    """Drop the graph cache for *workspace* after a migration mutates it.

    Migration bodies rewrite or relocate ``.vault/`` documents directly
    (``modified_stamp_backfill``, ``index_subfolder``) rather than through
    the mutating CLI verbs, so they never pass through
    :func:`vaultspec_core.cli._cache_hook.invalidate_graph_cache`. The
    per-file fingerprint in :mod:`vaultspec_core.graph.cache` self-heals
    against a content or file-set change regardless (a rewritten document
    changes size, a relocated one changes its manifest key), but that
    protection is an accident of what today's migrations happen to touch,
    not a guarantee: a future same-size, in-place rewrite would fall into
    the same accepted racily-clean residual window the mutating CLI verbs
    close by dropping the cache outright. Mirrors
    :func:`vaultspec_core.cli._cache_hook.invalidate_graph_cache` without
    importing the ``cli`` package, which would invert this module's
    dependency direction. Never raises: a missing cache, an unresolvable
    path, or a delete error all degrade to a no-op, because the fingerprint
    manifest remains a correct fallback guard and a failed invalidation
    must not turn a successful migration run into an error.

    Args:
        workspace: Workspace root whose graph cache should be invalidated.
    """
    from ..graph import cache as cache_mod

    try:
        cache_mod.cache_path(workspace).unlink(missing_ok=True)
    except OSError as exc:
        logger.debug("Graph cache invalidation skipped for %s: %s", workspace, exc)


class MigrationStatus(Enum):
    """High-level migration state for a workspace.

    Attributes:
        UP_TO_DATE: Manifest version covers every registered migration.
        PENDING: One or more registered migrations have a target version
            higher than the manifest's recorded ``vaultspec_version``.
        UNKNOWN: The workspace has no manifest (not installed) or the
            manifest is unreadable.
    """

    UP_TO_DATE = "up_to_date"
    PENDING = "pending"
    UNKNOWN = "unknown"


@dataclass
class MigrationResult:
    """Outcome of a single migration run.

    Attributes:
        name: Short identifier of the migration that produced this
            result. Matches the ``Migration.name`` field and the
            module-name slug.
        target_version: Release version that introduced the schema
            change, copied from :attr:`Migration.target_version`.
        summary: One-line operator-facing description of what the
            migration did, e.g. ``"relocated 12 feature indexes"``.
        counts: Free-form integer counters for additional structured
            detail (e.g. ``{"moved": 12, "skipped": 0}``).
    """

    name: str
    target_version: str
    summary: str
    counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Migration:
    """A single registered schema migration.

    Migration ``migrate`` callables must be idempotent: running them on
    an already-migrated workspace is required to be a true no-op (no
    filesystem mutation, no error, the returned :class:`MigrationResult`
    reports zero work).

    Attributes:
        target_version: Release version that introduced the schema
            change. Strict greater-than comparison against
            :attr:`vaultspec_core.core.manifest.ManifestData.vaultspec_version`
            decides whether the migration runs.
        name: Stable short identifier matching the module slug.
        migrate: Callable that performs the migration. Receives the
            workspace root path and returns a :class:`MigrationResult`.
    """

    target_version: str
    name: str
    migrate: Callable[[Path], MigrationResult]


_workspace_cache_lock = threading.Lock()
_workspace_cache: dict[Path, tuple[int, ...]] = {}
_notified_workspaces: set[Path] = set()


def reset_workspace_cache() -> None:
    """Drop the per-process caches of recently-checked workspaces.

    The authorised lazy trigger in
    :func:`vaultspec_core.cli._migration_hook.ensure_migrated` records
    each workspace it has already vetted so the manifest read does not
    repeat for every scan within a single CLI invocation, and
    :func:`warn_if_pending` records each workspace it has already
    warned about so a read emits the notice once rather than once per
    scan. Tests need a way to clear both between fixtures so each
    scenario starts from a clean slate.
    """
    with _workspace_cache_lock:
        _workspace_cache.clear()
        _notified_workspaces.clear()


def warn_if_pending(workspace: Path) -> list[str]:
    """Report pending migrations for *workspace* without running them.

    The read-side counterpart of :func:`run_pending_migrations`. A read
    path must not converge a stale workspace - the registry's entries
    delete and relocate tracked user documents, which no read
    authorised (issue #443) - but it must not stay silent about the
    drift either, or a workspace upgraded by a bare package install
    would be read through a legacy layout indefinitely with nothing
    ever saying so (the failure mode of issue #408, one layer up).

    Emits at most one warning per workspace per process: the notice is
    advice about workspace state, not about the individual scan, and
    repeating it once per :func:`~vaultspec_core.vaultcore.scanner.scan_vault`
    call would bury it. The same latch bounds the manifest read to one
    per workspace per process, so a warm read path pays a single set
    membership test.

    Never raises and never writes: an unreadable manifest, a missing
    workspace, or any other I/O failure degrades to "nothing pending",
    because a diagnostic that can break a read is worse than a
    diagnostic that is occasionally absent.

    Args:
        workspace: Workspace root directory.

    Returns:
        Names of the pending migrations, or an empty list when the
        workspace is up to date, uninstalled, unreadable, or has
        already been warned about in this process.
    """
    try:
        cache_key = workspace.resolve()
    except OSError:
        return []
    with _workspace_cache_lock:
        if cache_key in _notified_workspaces:
            return []
        _notified_workspaces.add(cache_key)
    try:
        status, names = migration_status(workspace)
    # Deliberately broad: a diagnostic that can break a read is worse
    # than a diagnostic that is occasionally absent.
    except Exception:
        logger.debug("Migration status unavailable for %s", workspace, exc_info=True)
        return []
    if status is not MigrationStatus.PENDING:
        return []
    logger.warning(
        "Workspace %s has pending schema migrations (%s); reads leave the "
        "workspace as found. Run 'vaultspec-core migrations run' to apply them.",
        workspace,
        ", ".join(names),
    )
    return names


def _build_registry() -> list[Migration]:
    """Assemble the ordered registry from the per-version migration modules.

    Imports each module lazily and returns the migrations sorted by
    parsed target version. Lazy imports keep the registry module
    cheap to import in code paths that never run migrations.
    """
    from .m_0_1_17_index_subfolder import MIGRATION as M_INDEX_SUBFOLDER
    from .m_0_1_20_gitignore_reversal import MIGRATION as M_GITIGNORE_REVERSAL
    from .m_0_1_21_frontmatter_lifecycle import MIGRATION as M_FRONTMATTER_LIFECYCLE
    from .m_0_1_24_codex_agents_dedup import MIGRATION as M_CODEX_AGENTS_DEDUP
    from .m_0_1_29_modified_stamp_backfill import MIGRATION as M_MODIFIED_STAMP_BACKFILL
    from .m_0_1_35_framework_flatten import MIGRATION as M_FRAMEWORK_FLATTEN
    from .m_0_1_48_launch_convergence import MIGRATION as M_LAUNCH_CONVERGENCE
    from .m_0_1_55_body_hash_seed import MIGRATION as M_BODY_HASH_SEED
    from .m_0_1_58_exec_ledger_fold import MIGRATION as M_EXEC_LEDGER_FOLD
    from .m_0_1_74_exec_ledger_only import MIGRATION as M_EXEC_LEDGER_ONLY

    entries: list[Migration] = [
        M_INDEX_SUBFOLDER,
        M_GITIGNORE_REVERSAL,
        M_FRONTMATTER_LIFECYCLE,
        M_CODEX_AGENTS_DEDUP,
        M_MODIFIED_STAMP_BACKFILL,
        M_FRAMEWORK_FLATTEN,
        M_LAUNCH_CONVERGENCE,
        M_BODY_HASH_SEED,
        M_EXEC_LEDGER_FOLD,
        M_EXEC_LEDGER_ONLY,
    ]
    return sorted(entries, key=lambda m: parse_version_tuple(m.target_version))


REGISTRY: list[Migration] = _build_registry()


def manifest_exists(workspace: Path) -> bool:
    """Report whether *workspace* carries a manifest at all.

    This is what separates "not installed" from "installed by a release
    that predates the version key". Both read back as an empty
    ``vaultspec_version``, and only one of them has migrations pending.
    """
    return (workspace / ".vaultspec" / MANIFEST_FILENAME).exists()


def list_pending(
    workspace: Path,
    *,
    manifest: ManifestData | None = None,
    registry: list[Migration] | None = None,
) -> list[Migration]:
    """Return every registered migration with a target above the manifest.

    Filters :data:`REGISTRY` to entries whose ``target_version`` is
    strictly greater than the manifest's ``vaultspec_version``. A
    workspace without a manifest (no ``providers.json``) is treated as
    a not-installed case and produces an empty list; the registry only
    runs against an installed workspace.

    A manifest that *exists* but carries no version is a different thing
    entirely: a legacy (v1.0) workspace, written before the version key
    existed. It predates every registered migration, so all of them are
    pending for it. Conflating the two made the workspaces most in need
    of the data-shape migrations the only ones that never received them,
    and nothing afterwards recorded that they had been skipped
    (issue #408). :func:`parse_version_tuple` already parses ``""`` to
    ``()`` precisely so it sorts below any real version; the comparison
    below needs no special case once the short-circuit is gone.

    Args:
        workspace: Workspace root directory.
        manifest: Optional pre-read :class:`ManifestData` to avoid a
            second :func:`read_manifest_data` call when the caller has
            already loaded it.

    Returns:
        List of pending :class:`Migration` instances in version order.
    """
    mdata = manifest if manifest is not None else read_manifest_data(workspace)
    if not mdata.vaultspec_version and not manifest_exists(workspace):
        return []
    current = parse_version_tuple(mdata.vaultspec_version)
    entries = sorted(
        REGISTRY if registry is None else registry,
        key=lambda m: parse_version_tuple(m.target_version),
    )
    return [m for m in entries if parse_version_tuple(m.target_version) > current]


def migration_status(
    workspace: Path,
    *,
    manifest: ManifestData | None = None,
    registry: list[Migration] | None = None,
) -> tuple[MigrationStatus, list[str]]:
    """Summarise the registry state for *workspace*.

    Args:
        workspace: Workspace root directory.
        manifest: Optional pre-read :class:`ManifestData` to avoid a
            second :func:`read_manifest_data` call when the caller has
            already loaded it.

    Returns:
        Two-tuple ``(status, names)`` where *status* is
        :class:`MigrationStatus` and *names* is the list of pending
        migration names (empty when ``status`` is
        :attr:`MigrationStatus.UP_TO_DATE` or
        :attr:`MigrationStatus.UNKNOWN`).
    """
    mdata = manifest if manifest is not None else read_manifest_data(workspace)
    if not mdata.vaultspec_version and not manifest_exists(workspace):
        # No manifest: nothing is installed, so there is nothing to say.
        # A manifest with no version is a legacy workspace and reports
        # PENDING like any other out-of-date one (issue #408).
        return MigrationStatus.UNKNOWN, []
    pending = list_pending(workspace, manifest=mdata, registry=registry)
    if not pending:
        return MigrationStatus.UP_TO_DATE, []
    return MigrationStatus.PENDING, [m.name for m in pending]


def run_pending_migrations(
    workspace: Path,
    *,
    use_cache: bool = False,
    registry: list[Migration] | None = None,
) -> list[MigrationResult]:
    """Run every registered migration whose target exceeds the manifest version.

    The driver reads :class:`vaultspec_core.core.manifest.ManifestData`,
    parses both the manifest and target versions via
    :func:`vaultspec_core.core.helpers.parse_version_tuple`, runs each
    pending migration in version order, then bumps
    :attr:`ManifestData.vaultspec_version` to the running package
    version on success. A migration that raises propagates the
    exception unchanged and prevents the version bump, so the next
    call re-attempts from the same starting version.

    Concurrency. The whole read-decide-migrate-bump cycle runs under
    :func:`vaultspec_core.core.helpers.advisory_lock` against the
    workspace's ``providers.json``. Concurrent invocations from
    different processes serialise on the OS-level file lock;
    concurrent invocations from the same process serialise on a
    per-path threading lock. The driver itself only calls
    :func:`read_manifest_data` and :func:`write_manifest_data`,
    neither of which acquires the lock - the lock is acquired here
    so the read-modify-write cycle stays atomic across concurrent
    invocations. Migration bodies must not invoke any wrapper that
    re-enters the lock (e.g. :func:`add_providers`,
    :func:`remove_provider`, or :func:`write_manifest`); entries
    mutate workspace content - ``.vault/`` documents or, for the
    ``framework_flatten`` entry, the ``.vaultspec/`` framework tree -
    but never the manifest, which is the documented contract for
    every entry.

    Authorisation. Every caller of this function is an explicit,
    mutating entry point: ``vaultspec-core install --upgrade``,
    ``vaultspec-core migrations run``, ``vaultspec-core vault repair``,
    and the two layout-sensitive authoring verbs behind
    :func:`vaultspec_core.cli._migration_hook.ensure_migrated`. Read
    paths call :func:`warn_if_pending` instead.

    Performance. The authorised lazy-trigger caller passes ``use_cache=True``;
    after the first up-to-date observation per workspace per process,
    every subsequent call short-circuits before acquiring the
    file lock or reading the manifest. Up-to-date workspaces pay the
    cost of a single :func:`dict.get` plus one tuple compare per
    ``scan_vault`` invocation.

    Args:
        workspace: Workspace root directory.
        use_cache: When ``True`` (the authorised lazy-trigger path used
            by the mutating authoring verbs), short-circuits on a
            per-process cache of workspaces previously seen up-to-date.
            Operator-facing triggers
            (``vaultspec-core migrations run`` and
            ``vaultspec-core install --upgrade``) pass ``False`` so they always
            consult the manifest.

    Returns:
        Per-migration :class:`MigrationResult` entries, in execution
        order. Empty when the workspace has no manifest or every
        registered migration is already covered.
    """
    registry_entries = sorted(
        REGISTRY if registry is None else registry,
        key=lambda m: parse_version_tuple(m.target_version),
    )

    # Resolve once so symlinked or relative invocations of the same
    # workspace share a cache entry rather than racing on equivalent
    # paths.
    cache_key = workspace.resolve()
    cached_version: tuple[int, ...] | None = None
    if use_cache:
        with _workspace_cache_lock:
            cached_version = _workspace_cache.get(cache_key)

    # REGISTRY is sorted ascending by target_version, so only the tail
    # entry matters: if its target is at or below the cached version,
    # every earlier entry is too. Empty registries trivially short-circuit.
    if cached_version is not None and (
        not registry_entries
        or parse_version_tuple(registry_entries[-1].target_version) <= cached_version
    ):
        return []

    manifest_path = workspace / ".vaultspec" / MANIFEST_FILENAME
    if not manifest_path.exists():
        # Non-vaultspec directory or freshly-scaffolded workspace
        # without a manifest yet. Skip the lock acquisition entirely
        # so the cost on these paths is one ``Path.exists`` syscall.
        return []

    with advisory_lock(manifest_path):
        manifest = read_manifest_data(workspace)
        # No short-circuit on an empty version here. The manifest's
        # existence was already established above, so an empty version
        # means a legacy workspace with every migration pending, not an
        # uninstalled one (issue #408).
        current = parse_version_tuple(manifest.vaultspec_version)
        pending = list_pending(workspace, manifest=manifest, registry=registry_entries)
        if not pending:
            if use_cache:
                with _workspace_cache_lock:
                    _workspace_cache[cache_key] = current
            return []

        # Incremental bumps: after each migration succeeds, write the
        # manifest version up to that migration's target. If a later
        # migration in the chain raises, the manifest already reflects
        # the work that did succeed, so the next invocation skips the
        # already-applied entries and re-attempts only the failing one.
        # ``pending`` is pre-filtered to entries strictly above the
        # current manifest version and REGISTRY is sorted ascending,
        # so each iteration's target is monotonically greater than the
        # previous on-disk version - no per-iteration version check is
        # required to guard the bump.
        results: list[MigrationResult] = []
        for migration in pending:
            logger.info(
                "Running migration %s (target_version=%s)",
                migration.name,
                migration.target_version,
            )
            result = migration.migrate(workspace)
            logger.info("vaultspec migration: %s", result.summary)
            results.append(result)

            # Invalidate immediately after each migration body returns, not
            # once after the whole loop: a later entry in the same run can
            # still raise, and this migration's mutation must not be left
            # behind a graph cache that predates it. See
            # `_invalidate_graph_cache` for why this cannot rely solely on
            # the per-file fingerprint self-healing.
            _invalidate_graph_cache(workspace)

            manifest.vaultspec_version = migration.target_version
            write_manifest_data(workspace, manifest)

        # Final bump to the running package version when it exceeds
        # the highest-target migration we just applied. In production
        # the running version always equals or exceeds the most recent
        # registered target; the dual case is exercised only in tests
        # that synthesise migrations targeting a future version.
        running = package_version()
        if parse_version_tuple(running) > parse_version_tuple(
            manifest.vaultspec_version
        ):
            manifest.vaultspec_version = running
            write_manifest_data(workspace, manifest)

        if use_cache:
            with _workspace_cache_lock:
                _workspace_cache[cache_key] = parse_version_tuple(
                    manifest.vaultspec_version
                )

        return results
