"""Shared graph-cache invalidation hook for mutating vault verbs.

Every CLI verb that writes or moves a ``.vault/`` document changes the
corpus the fingerprint graph cache was built over.  The fingerprint
manifest (size, mtime, content hash per file) is the cache's passive guard,
but it is not the *only* guard: after a known mutation the verb explicitly
drops the cache so the next :class:`~vaultspec_core.graph.api.VaultGraph`
build cannot serve pre-mutation data even in the pathological case where a
write lands within a single ``st_mtime_ns`` tick without changing a file's
size.  This makes "stale never trusted" hold by construction after a CLI
mutation rather than relying on timestamp resolution alone.

Verbs call :func:`invalidate_graph_cache` after a successful, non-dry-run
write.  Dropping the cache file is idempotent and cheap: a missing cache is
simply a miss on the next build, which rebuilds from the corpus and rewrites
a fresh cache.

Schema migrations mutate ``.vault/`` documents outside this hook - a
migration body runs ahead of the layout-sensitive authoring verbs, from
:func:`vaultspec_core.cli._migration_hook.ensure_migrated` - so
:func:`vaultspec_core.migrations.run_pending_migrations` carries its own
equivalent invalidation call rather than importing this module (which would
invert the ``migrations`` -> ``cli`` dependency direction). See
:func:`vaultspec_core.migrations._invalidate_graph_cache`.  That hook is this
one's write-side mirror: it converges the schema before such a write, this
one drops the cache after it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["invalidate_graph_cache"]


def invalidate_graph_cache(root_dir: Path) -> None:
    """Drop the graph cache for *root_dir* after a document mutation.

    Removes the on-disk cache file so the next graph build rebuilds from the
    current corpus.  Never raises: a missing cache, an unresolvable path, or
    a delete error all degrade to a no-op, because the fingerprint manifest
    remains a correct fallback guard and a failed invalidation must not break
    the mutating verb that triggered it.

    Args:
        root_dir: Project root whose graph cache should be invalidated.
    """
    from ..graph import cache as cache_mod

    try:
        path = cache_mod.cache_path(root_dir)
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.debug("Graph cache invalidation skipped for %s: %s", root_dir, exc)
