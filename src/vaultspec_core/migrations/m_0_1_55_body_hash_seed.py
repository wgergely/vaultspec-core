"""Seed the ``body_hash`` content fingerprint across an existing vault.

Introduced for vaultspec-core 0.1.55 as the data counterpart of the
modified-stamp-provenance ADR. Staleness of the ``modified:`` stamp is no
longer inferred from file mtime but from a machine-maintained fingerprint
of the document body, written beside the stamp by every stamping path. A
document that carries no fingerprint attests nothing about its body and is
therefore silent - correct, but permanently silent for every document
written before the field existed. This migration walks the ``.vault`` tree
once and attests each document's body exactly as it stands, so
reconciliation begins working corpus-wide from the seed forward.

The migration writes facts, not inferences. The value it stores is the
fingerprint of the body already on disk; nothing about the document's
history is guessed. In particular ``modified:`` values are left untouched.
They are known to carry inherited inaccuracy, but every available
recomputation source is worse - mtime is the defect being removed, and git
history on this corpus is polluted by the bulk stamp-rewrite commits
themselves - so the stamps stand as they are under amnesty and correctness
restarts at seed time.

Idempotent by construction: a document that already carries a canonical
``body_hash:`` is left byte-for-byte untouched, and re-seeding an
unchanged body would compute the identical digest in any case. A document
whose frontmatter offers no anchor for the field (no ``body_schema:``, no
``modified:``, no ``date:``) is skipped and counted; the field has no
canonical position there, and the migration never invents one.

See also:
    :mod:`vaultspec_core.migrations` for the registry driver.
    :mod:`vaultspec_core.vaultcore.body_hash` for the fingerprint's
    canonical definition.
    :func:`vaultspec_core.vaultcore.checks.modified_stamp.check_modified_stamp`
    for the reconciliation path the seed enables.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import Migration, MigrationError, MigrationResult

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["MIGRATION", "migrate"]

logger = logging.getLogger(__name__)

_TARGET_VERSION = "0.1.55"
_NAME = "body_hash_seed"


def migrate(workspace: Path) -> MigrationResult:
    """Attest every vault document's current body with a ``body_hash:``.

    Walks ``<workspace>/<docs_dir>/`` for every ``*.md`` document and
    writes the fingerprint of its body into frontmatter unless the
    document already carries a canonical one. No other field is touched.

    Args:
        workspace: Workspace root directory.

    Returns:
        :class:`MigrationResult` whose ``counts`` carry ``seeded``
        (fingerprints written), ``already`` (documents already carrying a
        canonical fingerprint), and ``skipped`` (no frontmatter anchor for
        the field).

    Raises:
        MigrationError: When a document that needs a fingerprint cannot be
            read or written. The driver propagates the exception unchanged
            so the manifest version is not bumped and the next invocation
            retries from the same starting version.
    """
    from ..config import get_config
    from ..vaultcore import parse_vault_metadata
    from ..vaultcore.body_hash import is_canonical_digest
    from ..vaultcore.checks.modified_stamp import seed_body_hash
    from ..vaultcore.exclusions import is_excluded_vault_path

    cfg = get_config()
    docs_dir = workspace / cfg.docs_dir
    counts = {"seeded": 0, "already": 0, "skipped": 0}
    if not docs_dir.is_dir():
        return MigrationResult(
            name=_NAME,
            target_version=_TARGET_VERSION,
            summary="no .vault/ directory; nothing to seed",
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

        metadata, _body = parse_vault_metadata(content)
        if is_canonical_digest(metadata.body_hash):
            counts["already"] += 1
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
            written = seed_body_hash(doc, root_dir=None)
        except OSError as exc:
            raise MigrationError(
                f"{_NAME}: failed to write body hash to {doc}: {exc}"
            ) from exc

        if written:
            counts["seeded"] += 1
            logger.info("Migration %s: seeded %s", _NAME, doc)
        else:
            # No frontmatter anchor to insert the field after, so the
            # fingerprint cannot land in its canonical position; record the
            # document as skipped rather than silently claiming a seed.
            counts["skipped"] += 1
            logger.info(
                "Migration %s: skipped %s; no frontmatter anchor for the field",
                _NAME,
                doc,
            )

    seeded = counts["seeded"]
    summary = (
        f"seeded body fingerprint on {seeded} "
        f"{'document' if seeded == 1 else 'documents'}"
    )
    if counts["skipped"]:
        summary += f" ({counts['skipped']} skipped, no frontmatter anchor)"

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
