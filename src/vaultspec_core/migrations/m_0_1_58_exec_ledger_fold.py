"""Fold per-Step execution records into one consolidated ledger per plan.

Introduced for vaultspec-core 0.1.58 as the data counterpart of the
exec-record-consolidation ADR. A ``body-v1`` corpus stores one document per
plan Step, which on the measured production vault is 7,362 files and 17.9 MB
- 38% of the vault by bytes and 66% of its files - of which 83.8% is prose no
consumer reads. This migration folds each plan's records into a single
append-only ledger, recovering the machine-usable content - rows, and any
notes the record carried - and discarding the rest of the prose.

Unlike every migration before it, this one **removes documents**. That is the
schema change: consolidation is not expressible as an additive rewrite. The
removal is ordered so it cannot lose data - the ledger carrying a record's
content is written and flushed before that record is unlinked, so an
interruption leaves duplication rather than loss - and the discarded bodies
remain in the commit preceding the migration, because ``.vault/`` is tracked.
There is, however, no forward command that restores them.

The migration writes facts, not inferences. A row recovered from a
``## Scope`` section carries the paths the scaffolder filled from the
originating Step row and states no operation: that schema did not record
whether a path was added, modified, or deleted, so the row carries ``T``
(touched), which stays distinguishable from an operation an executor
actually reported.

``body-v1`` is a schema declaration, not a body shape, and the two do not
coincide. A pre-ledger record carried the same ``## Changes`` contract
without the Step column (see
:mod:`vaultspec_core.vaultcore.exec_ledger`), so a record declaring
``body-v1`` may hold real operations and a ``## Notes`` section. The planner
recovers both from such a record, and the ledger is written with both: this
migration shares :func:`~vaultspec_core.vaultcore.exec_fold.apply_fold` with
``vault exec fold`` rather than restating the write, because a local copy of
it silently dropped those notes while unlinking the records that held them.

Records that cannot be attributed to a single Step are left untouched: one
with no ``step_id``, and a Phase summary, which rolls up Steps rather than
documenting one. Folding either would drop evidence the ledger cannot carry.

Scope is deliberately narrow: only records declaring a pre-``body-v2``
schema fold. A current-schema per-Step record is a legitimate document, not
legacy shape, and consolidating it is the operator's call through
``vault exec fold``. This matters because the driver bumps the manifest to the
running package version rather than a migration's target, so a workspace on a
pre-release build re-runs the registry on every vault command - and a
migration that folded current records would silently eat freshly authored
ones.

Idempotent by construction: the planner refuses to fold a ledger into itself,
a folded corpus offers no per-Step records to fold, and anything written after
the fold declares the current schema, so a second run plans nothing and
touches no file.

See also:
    :mod:`vaultspec_core.migrations` for the registry driver.
    :mod:`vaultspec_core.vaultcore.exec_fold` for the pure fold planner.
    :mod:`vaultspec_core.vaultcore.exec_ledger` for the row grammar.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from . import Migration, MigrationError, MigrationResult

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["MIGRATION", "migrate"]

logger = logging.getLogger(__name__)

_TARGET_VERSION = "0.1.58"
_NAME = "exec_ledger_fold"


def _plan_stem_from(related: object, fallback: str) -> str:
    """Return the parent-plan stem named in *related*, or *fallback*."""
    from ..vaultcore.checks.exec_mapping import link_stem

    if not isinstance(related, list):
        return fallback
    # Frontmatter is untyped data, so the list is narrowed before iteration
    # rather than suppressed at the use site.
    links: tuple[object, ...] = tuple(cast("list[object]", related))
    for link in links:
        stem = link_stem(str(link))
        if stem and stem.endswith("-plan"):
            return stem
    return fallback


def migrate(workspace: Path) -> MigrationResult:
    """Fold every feature's per-Step execution records into one ledger each.

    Args:
        workspace: Workspace root directory.

    Returns:
        :class:`MigrationResult` whose ``counts`` carry ``folders`` (feature
        folders consolidated), ``folded`` (records removed), ``rows`` (ledger
        rows written), ``notes`` (note lines carried), ``paths`` (scope paths
        recovered), and ``skipped`` (records deliberately left intact).

    Raises:
        MigrationError: When a ledger cannot be written or a folded record
            cannot be removed. The driver propagates it unchanged so the
            manifest version is not bumped and the next invocation retries.
    """
    from ..config import get_config
    from ..vaultcore import parse_vault_metadata
    from ..vaultcore.body_schema import CURRENT_BODY_SCHEMA
    from ..vaultcore.exec_fold import apply_fold, plan_fold, sources_from

    cfg = get_config()
    exec_dir = workspace / cfg.docs_dir / "exec"
    counts = {
        "folders": 0,
        "folded": 0,
        "rows": 0,
        "notes": 0,
        "paths": 0,
        "skipped": 0,
        "current": 0,
    }
    if not exec_dir.is_dir():
        return MigrationResult(
            name=_NAME,
            target_version=_TARGET_VERSION,
            summary="no .vault/exec/ directory; nothing to fold",
            counts=counts,
        )

    for folder in sorted(item for item in exec_dir.iterdir() if item.is_dir()):
        records: list[tuple[Path, str | None, str]] = []
        plan_stem = f"{folder.name}-plan"
        feature = folder.name[11:] or folder.name

        for doc in sorted(folder.glob("*.md")):
            try:
                content = doc.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise MigrationError(f"{_NAME}: failed to read {doc}: {exc}") from exc
            metadata, body = parse_vault_metadata(content)
            plan_stem = _plan_stem_from(metadata.related, plan_stem)
            if metadata.body_schema == CURRENT_BODY_SCHEMA:
                # A current-schema per-Step record is a legitimate document,
                # not legacy shape. Folding it is the operator's call through
                # `vault exec fold`, never a migration's: the manifest bumps
                # to the running package version rather than this migration's
                # target, so a pre-release workspace re-runs the registry on
                # every vault command, and folding current records would make
                # that silently eat freshly authored ones.
                counts["current"] += 1
                continue
            records.append((doc, metadata.step_id, body))

        plan = plan_fold(sources_from(records))
        if plan.is_empty:
            counts["skipped"] += len(plan.skipped)
            continue

        # The shared writer, never a local copy of it: it appends the rows
        # *and* the notes the planner recovered, and unlinks a record only
        # once the ledger is confirmed to carry both. A second definition of
        # this conversion is exactly how the notes came to be dropped here.
        try:
            ledger_path = apply_fold(
                workspace,
                plan,
                feature=feature,
                folder_date=folder.name[:10],
                plan_stem=plan_stem,
            )
        except (OSError, ValueError) as exc:
            raise MigrationError(
                f"{_NAME}: failed to fold {folder.name}: {exc}"
            ) from exc

        counts["folders"] += 1
        counts["folded"] += len(plan.folded)
        counts["rows"] += len(plan.rows)
        counts["notes"] += len(plan.notes)
        counts["paths"] += plan.recovered_paths
        counts["skipped"] += len(plan.skipped)
        logger.info(
            "Migration %s: folded %d record(s) of %s into %s",
            _NAME,
            len(plan.folded),
            folder.name,
            ledger_path.name,
        )

    folded = counts["folded"]
    if not folded:
        summary = "no per-Step execution records to fold"
    else:
        summary = (
            f"folded {folded} execution "
            f"{'record' if folded == 1 else 'records'} into "
            f"{counts['folders']} {'ledger' if counts['folders'] == 1 else 'ledgers'} "
            f"({counts['paths']} scope path(s) recovered)"
        )
    if counts["skipped"]:
        summary += f"; {counts['skipped']} left intact"
    if counts["current"]:
        summary += f"; {counts['current']} current-schema record(s) untouched"

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
