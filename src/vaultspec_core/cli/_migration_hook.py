"""Authorised schema-convergence hook for layout-sensitive authoring verbs.

The migration registry rewrites, relocates, and deletes tracked ``.vault/``
documents.  That is a mutation, so it needs a caller who asked for one.  The
trigger used to live inside
:func:`vaultspec_core.vaultcore.scanner.scan_vault`, which every read shares:
a read-only MCP ``find`` therefore ran the ``exec_ledger_only`` migration and
deleted 47 tracked documents out of a clean worktree (issue #443).

The boundary is now drawn by *write intent to a schema-decided location*, not
by "is this a vault command":

- ``vaultspec-core install --upgrade``, ``vaultspec-core migrations run`` and
  ``vaultspec-core vault repair`` converge because converging is what the
  operator invoked them for.  They call
  :func:`vaultspec_core.migrations.run_pending_migrations` directly.
- ``vaultspec-core vault add`` and ``vaultspec-core vault feature index``
  converge through :func:`ensure_migrated` because *where* they write is
  decided by the schema.  A generated feature index written against a legacy
  layout leaves the workspace with two indexes for one feature, one at the
  legacy root and one under ``.vault/index/`` - the split brain that put the
  trigger in the scanner in the first place.
- Nothing else converges.  Verbs that edit, link, archive, or log against a
  document the *user named* (``vault edit``, ``vault link``, ``vault archive``,
  ``vault exec``, ``plan step check``) write to a path they were handed, so a
  stale layout elsewhere in the workspace cannot misplace their write.  They
  have no more standing to rewrite 47 unrelated documents than a read does.
- Reads converge nothing and instead surface the drift through
  :func:`vaultspec_core.migrations.warn_if_pending`.

This module is the write-side mirror of
:mod:`vaultspec_core.cli._cache_hook`: a verb that must drop the graph cache
*after* it writes is a verb whose write the schema might have placed, and the
two hooks bracket exactly such a write.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["ensure_migrated"]


def ensure_migrated(root_dir: Path) -> None:
    """Apply pending schema migrations before a layout-sensitive write.

    Delegates to :func:`vaultspec_core.migrations.run_pending_migrations`
    with the per-process workspace cache enabled, so a workspace already
    observed up to date costs one dictionary lookup rather than a manifest
    read and an advisory lock.

    Unlike :func:`vaultspec_core.cli._cache_hook.invalidate_graph_cache`,
    this **does** propagate.  A failed cache invalidation is recoverable -
    the fingerprint manifest still guards the next build - but a failed
    migration means the verb is about to write into a layout the schema no
    longer describes, which is the split brain this hook exists to prevent.
    The caller surfaces the failure rather than writing anyway.

    Args:
        root_dir: Workspace root about to be written to.

    Raises:
        Exception: Whatever the failing migration body raised, unchanged,
            so the manifest version bump stays suppressed and the operator
            sees the real cause.
    """
    from ..migrations import run_pending_migrations

    try:
        run_pending_migrations(root_dir, use_cache=True)
    except Exception:
        logger.exception("Pending migration failed for %s", root_dir)
        raise
