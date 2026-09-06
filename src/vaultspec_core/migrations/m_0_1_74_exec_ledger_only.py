"""Fold every remaining per-Step execution record into its plan's ledger.

Introduced for vaultspec-core 0.1.74, the release in which the ledger became
the only execution artifact: ``vault add exec`` refuses, the per-Step and
Phase-summary templates are gone, and ``exec-mapping`` reports a per-Step
record as an error. This migration converges an upgraded workspace so that
error never fires on records the previous release authored legitimately.

The 0.1.58 fold deliberately left ``body-v2`` records alone because
``vault add exec --step`` was still the default authoring path and a
re-running registry would have eaten freshly authored records. That hazard
ends with the refusal shipping in the same release, so this migration folds
every record carrying a ``step_id`` regardless of schema, including the flat
``<date>-<feature>-exec.md`` shape from before Step-aware scaffolding, and
removes each Phase Summary whose every Step has rows in the ledger.

Recovery is faithful to what each record actually stated: a ``body-v2``
record's rows keep their operations and ``verify:`` line and its ``## Notes``
lines are carried under the Step id; a ``body-v1`` record's Scope paths
become ``T`` rows and its prose is discarded. Records with no ``step_id``
and summaries whose Steps are not all logged are left intact. Removal is
ordered so it cannot lose data: the ledger is written before any record is
unlinked. Idempotent by construction: a second run finds no per-Step record
and plans nothing.

See also:
    :mod:`vaultspec_core.vaultcore.exec_fold` for the shared planner and
    writer this migration and ``vault exec fold`` both use.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import Migration, MigrationError, MigrationResult

if TYPE_CHECKING:
    from pathlib import Path

    from ..vaultcore.exec_fold import FoldPlan

__all__ = ["MIGRATION", "migrate", "preview"]

logger = logging.getLogger(__name__)

_TARGET_VERSION = "0.1.74"
_NAME = "exec_ledger_only"


def _feature_of(folder_name: str, plan_stem: str | None) -> str:
    """Derive the feature tag from an exec folder name or a plan stem."""
    if plan_stem and plan_stem.endswith("-plan"):
        return plan_stem[11:-5] or folder_name[11:]
    return folder_name[11:] or folder_name


@dataclass(frozen=True)
class _FolderFold:
    """One exec folder's decided fold, before anything is written."""

    folder_name: str
    plan_stem: str
    feature: str
    plan: FoldPlan


def _plan_folds(workspace: Path) -> list[_FolderFold]:
    """Decide every folder's fold without writing or removing anything.

    The whole decision the migration makes, in one read-only pass:
    :func:`migrate` applies what this returns and :func:`preview` reports
    it, so the preview an operator reads is the run they get.

    Args:
        workspace: Workspace root directory.

    Returns:
        One entry per exec folder with a non-empty fold, in folder order.
    """
    from ..config import get_config
    from ..vaultcore.exec_fold import (
        collect_sources,
        phase_steps_of,
        plan_fold,
        sources_from,
    )
    from ..vaultcore.parser import parse_vault_metadata

    cfg = get_config()
    docs_dir = workspace / cfg.docs_dir
    exec_dir = docs_dir / "exec"
    if not exec_dir.is_dir():
        return []

    # Group candidates by exec folder. A flat record joins the folder its
    # parent plan names, so its rows land in that plan's ledger.
    groups: dict[str, list[Path]] = {}
    for folder in sorted(item for item in exec_dir.iterdir() if item.is_dir()):
        groups.setdefault(folder.name, []).extend(sorted(folder.glob("*.md")))
    for flat in sorted(item for item in exec_dir.glob("*.md") if item.is_file()):
        try:
            metadata, _ = parse_vault_metadata(flat.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if not metadata.step_id:
            continue
        _, plan_stem, _ = collect_sources([flat])
        if not plan_stem:
            continue
        groups.setdefault(plan_stem[: -len("-plan")], []).append(flat)

    folds: list[_FolderFold] = []
    for folder_name, paths in sorted(groups.items()):
        records, plan_stem, covered = collect_sources(paths)
        plan_stem = plan_stem or f"{folder_name}-plan"
        plan_path = docs_dir / "plan" / f"{plan_stem}.md"
        folds.append(
            _FolderFold(
                folder_name=folder_name,
                plan_stem=plan_stem,
                feature=_feature_of(folder_name, plan_stem),
                plan=plan_fold(
                    sources_from(records),
                    phase_steps=phase_steps_of(plan_path),
                    covered=covered,
                ),
            )
        )
    return folds


def preview(workspace: Path) -> list[Path]:
    """Return every record this migration would remove from *workspace*.

    Args:
        workspace: Workspace root directory.

    The set comes from :func:`~vaultspec_core.vaultcore.exec_fold.removals_of`,
    the same call ``apply_fold`` makes to decide what to unlink, so the
    preview cannot describe a different run from the one it precedes.

    Returns:
        The removal set in execution order. A planner that decides to fold
        nothing, or that recovers nothing to write in place of what it would
        remove, yields an empty list.
    """
    from ..vaultcore.exec_fold import removals_of

    return [
        path
        for fold in _plan_folds(workspace)
        if not fold.plan.is_empty
        for path in removals_of(fold.plan)
    ]


def migrate(workspace: Path) -> MigrationResult:
    """Fold every per-Step execution record into its plan's ledger.

    Every record this removes is copied into ``.vault/.trash/`` first, in
    one snapshot directory for the whole run, and a snapshot that cannot be
    written aborts the migration with nothing deleted.

    Args:
        workspace: Workspace root directory.

    Returns:
        :class:`MigrationResult` whose ``counts`` carry ``folders`` (ledgers
        written), ``folded`` (records removed), ``summaries`` (Phase
        Summaries removed), ``rows``, ``notes``, ``paths``, ``skipped``, and
        ``snapshot_bytes``, and whose ``snapshot`` names the backup
        directory.

    Raises:
        MigrationError: When a ledger cannot be written, a folded record
            cannot be removed, or the removals cannot be snapshotted; the
            driver then leaves the manifest version unchanged so the next
            invocation retries.
    """
    from ..config import get_config
    from ..vaultcore.exec_fold import apply_fold
    from ..vaultcore.trash import SnapshotError, TrashWriter

    cfg = get_config()
    counts = {
        "folders": 0,
        "folded": 0,
        "summaries": 0,
        "rows": 0,
        "notes": 0,
        "paths": 0,
        "skipped": 0,
        "snapshot_bytes": 0,
    }
    if not (workspace / cfg.docs_dir / "exec").is_dir():
        return MigrationResult(
            name=_NAME,
            target_version=_TARGET_VERSION,
            summary="no .vault/exec/ directory; nothing to fold",
            counts=counts,
        )

    # One writer for the whole run, so an operator recovering from this
    # migration has one directory to look in rather than one per folder.
    trash = TrashWriter(workspace, _NAME)

    for fold in _plan_folds(workspace):
        plan = fold.plan
        counts["skipped"] += len(plan.skipped)
        if plan.is_empty:
            continue

        try:
            outcome = apply_fold(
                workspace,
                plan,
                feature=fold.feature,
                folder_date=fold.folder_name[:10],
                plan_stem=fold.plan_stem,
                trash=trash,
            )
        except SnapshotError as exc:
            raise MigrationError(
                f"{_NAME}: refusing to fold {fold.folder_name} without a backup: {exc}"
            ) from exc
        except (OSError, ValueError) as exc:
            raise MigrationError(
                f"{_NAME}: failed to fold {fold.folder_name}: {exc}"
            ) from exc

        counts["folders"] += 1
        counts["folded"] += len(plan.folded)
        counts["summaries"] += len(plan.summaries)
        counts["rows"] += len(plan.rows)
        counts["notes"] += len(plan.notes)
        counts["paths"] += plan.recovered_paths
        logger.info(
            "Migration %s: folded %d record(s), removed %d summary(ies) of %s into %s",
            _NAME,
            len(plan.folded),
            len(plan.summaries),
            fold.folder_name,
            outcome.ledger_path.name,
        )

    snapshot = trash.result()
    if snapshot is not None:
        counts["snapshot_bytes"] = snapshot.total_bytes

    folded = counts["folded"]
    if not folded and not counts["summaries"]:
        summary = "no per-Step execution records to fold"
    else:
        summary = (
            f"folded {folded} execution "
            f"{'record' if folded == 1 else 'records'} into "
            f"{counts['folders']} {'ledger' if counts['folders'] == 1 else 'ledgers'} "
            f"({counts['paths']} path(s) recovered, "
            f"{counts['summaries']} summary(ies) removed)"
        )
    if counts["skipped"]:
        summary += f"; {counts['skipped']} left intact"
    if snapshot is not None:
        summary += f"; {snapshot.files} copied to {cfg.docs_dir}/.trash/"

    return MigrationResult(
        name=_NAME,
        target_version=_TARGET_VERSION,
        summary=summary,
        counts=counts,
        snapshot=str(snapshot.root) if snapshot is not None else None,
    )


MIGRATION = Migration(
    target_version=_TARGET_VERSION,
    name=_NAME,
    migrate=migrate,
    preview=preview,
)
