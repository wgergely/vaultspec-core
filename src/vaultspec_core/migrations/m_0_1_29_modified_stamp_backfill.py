"""Backfill the ``modified:`` frontmatter stamp on pre-existing documents.

Introduced for vaultspec-core 0.1.29 as the data counterpart of the
vault-orientation ADR (decisions D3, D3a). The ``modified:`` recency
stamp lands equal to ``date:`` at scaffold time on every newly created
document, but documents written before the stamp shipped carry no such
field. This migration walks the ``.vault`` tree once and inserts a
canonical ``modified:`` stamp into every document that lacks one, so the
vault status rollup has a recency source for the whole corpus rather than
only for documents created after the feature shipped.

Backfill value, in order of preference:

1. the leniently-parsed ``date:`` field, rewritten to canonical
   ``yyyy-mm-dd`` form;
2. the document's filename ``yyyy-mm-dd`` prefix when ``date:`` is absent
   or itself unparseable;
3. otherwise the document is skipped and the reason recorded - there is
   no defensible date to stamp and the migration never invents one.

The migration is strictly additive and idempotent: a document that
already carries any ``modified:`` field is left byte-for-byte untouched
(its value, canonical or not, is the reconciliation checker's concern,
not the backfill's), and a second run over an already-backfilled vault
performs no filesystem mutation. Insertion reuses the modified-stamp
checker's writer so the source CRLF/LF convention and the canonical
schema position (directly after ``date:``) are preserved.

See also:
    :mod:`vaultspec_core.migrations` for the registry driver.
    :func:`vaultspec_core.vaultcore.checks.modified_stamp.check_modified_stamp`
    for the live-edit reconciliation path that normalizes and refreshes
    stamps after the backfill has seeded them.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import Migration, MigrationError, MigrationResult

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["MIGRATION", "migrate"]

logger = logging.getLogger(__name__)

_TARGET_VERSION = "0.1.29"
_NAME = "modified_stamp_backfill"


def migrate(workspace: Path) -> MigrationResult:
    """Backfill ``modified:`` from ``date:`` across the workspace's vault.

    Walks ``<workspace>/<docs_dir>/`` for every ``*.md`` document, and for
    each one that has no ``modified:`` field inserts a canonical stamp
    derived from the leniently-parsed ``date:`` field, falling back to the
    filename ``yyyy-mm-dd`` prefix. Documents that already carry the field
    are left untouched, making the migration idempotent. A document with
    neither a parseable ``date:`` nor a filename date prefix is skipped and
    counted under ``skipped``.

    Args:
        workspace: Workspace root directory.

    Returns:
        :class:`MigrationResult` whose ``counts`` carry ``backfilled``
        (stamps inserted), ``skipped`` (no defensible date), and
        ``already`` (documents that already had the field).

    Raises:
        MigrationError: When a document that needs a stamp cannot be read
            or written. The driver propagates the exception unchanged so
            the manifest version is not bumped and the next invocation
            retries from the same starting version.
    """
    from ..config import get_config
    from ..vaultcore import normalize_date, parse_vault_metadata
    from ..vaultcore.checks.modified_stamp import filename_date, write_stamp
    from ..vaultcore.exclusions import is_excluded_vault_path

    cfg = get_config()
    docs_dir = workspace / cfg.docs_dir
    counts = {"backfilled": 0, "skipped": 0, "already": 0}
    if not docs_dir.is_dir():
        return MigrationResult(
            name=_NAME,
            target_version=_TARGET_VERSION,
            summary="no .vault/ directory; nothing to backfill",
            counts=counts,
        )

    documents = sorted(
        item
        for item in docs_dir.rglob("*.md")
        if item.is_file() and not is_excluded_vault_path(item.relative_to(docs_dir))
    )

    for doc in documents:
        try:
            content = doc.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise MigrationError(f"{_NAME}: failed to read {doc}: {exc}") from exc

        metadata, _ = parse_vault_metadata(content)
        if metadata.modified:
            counts["already"] += 1
            continue

        value = normalize_date(metadata.date) or filename_date(doc)
        if value is None:
            counts["skipped"] += 1
            logger.info(
                "Migration %s: skipped %s; no parseable date or filename prefix",
                _NAME,
                doc,
            )
            continue

        try:
            # ``root_dir=None`` runs the rewrite without the per-document
            # advisory lock, deliberately. This body already executes inside
            # the migration driver's manifest lock, and the lock primitive is
            # a non-reentrant sentinel with no timeout: adding a
            # manifest-to-document edge here would make any future caller
            # that holds a document lock and reaches the lazy migration
            # trigger (``scan_vault`` runs it) an unrecoverable hang rather
            # than a contended wait. Migrations run once per workspace at a
            # version boundary, so the exposure they buy back is far smaller
            # than the failure mode they would introduce.
            written = write_stamp(doc, value, root_dir=None)
        except OSError as exc:
            raise MigrationError(
                f"{_NAME}: failed to write stamp to {doc}: {exc}"
            ) from exc

        if written:
            counts["backfilled"] += 1
            logger.info("Migration %s: backfilled %s with %s", _NAME, doc, value)
        else:
            # No ``date:`` anchor in the frontmatter to insert after, so
            # the stamp cannot land in its canonical position; record the
            # document as skipped rather than silently claiming a backfill.
            counts["skipped"] += 1
            logger.info(
                "Migration %s: skipped %s; no date anchor for stamp insertion",
                _NAME,
                doc,
            )

    backfilled = counts["backfilled"]
    summary = (
        f"backfilled modified stamp on {backfilled} "
        f"{'document' if backfilled == 1 else 'documents'}"
    )
    if counts["skipped"]:
        summary += f" ({counts['skipped']} skipped, no defensible date)"

    return MigrationResult(
        name=_NAME,
        target_version=_TARGET_VERSION,
        summary=summary,
        counts=counts,
    )


MIGRATION = Migration(
    target_version=_TARGET_VERSION,
    name=_NAME,
    migrate=migrate,
)
