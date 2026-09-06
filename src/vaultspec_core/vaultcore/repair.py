"""Repair pipeline orchestration for vault content recovery.

The repair pipeline is intentionally separate from individual checkers:
``vault check all --fix`` remains a check-level compatibility surface,
while this module models an operator recovery run with preflight,
diagnosis, optional mutation, generated-index refresh, and postcheck
phases.
"""

from __future__ import annotations

import logging
import pathlib
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from ..core.windowing import windowed_section
from ..migrations import MigrationStatus, migration_status, run_pending_migrations
from .checks import CheckDiagnostic, CheckResult, Severity, run_all_checks

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from ..graph.cache import Fingerprint

__all__ = [
    "RepairPhase",
    "RepairRun",
    "run_repair_pipeline",
]

_FINGERPRINT_EXCLUDED_DIR_NAMES = frozenset({"data", "logs", "_archive"})

#: Deleted paths carried on the preflight payload before the rest are counted.
_DELETION_PREVIEW_LIMIT = 50

logger = logging.getLogger(__name__)


class RepairPhase(StrEnum):
    """Named phases emitted by ``vaultspec-core vault repair``."""

    PREFLIGHT = "preflight"
    CHECK = "check"
    FIX = "fix"
    INDEX = "index"
    POSTCHECK = "postcheck"
    SUMMARY = "summary"


@dataclass
class RepairRun:
    """Structured result from a vault repair pipeline run."""

    dry_run: bool
    feature: str | None = None
    include_index: bool = True
    partial_failure: bool = False
    phases: list[dict[str, Any]] = field(default_factory=list)
    journal: list[dict[str, Any]] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    generated_indexes: list[str] = field(default_factory=list)
    planned_fixes: list[dict[str, Any]] = field(default_factory=list)
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    root_causes: list[dict[str, Any]] = field(default_factory=list)
    postcheck: list[CheckResult] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        """Number of postcheck ERROR diagnostics."""
        return sum(result.error_count for result in self.postcheck) + int(
            self.partial_failure
        )

    @property
    def warning_count(self) -> int:
        """Number of postcheck WARNING diagnostics."""
        return sum(result.warning_count for result in self.postcheck)

    @property
    def fixed_count(self) -> int:
        """Total fixes applied by the mutating check pass."""
        return sum(
            int(phase.get("fixed_count", 0))
            for phase in self.phases
            if phase.get("phase") == RepairPhase.FIX.value
        )


@dataclass
class _PipelineState:
    """Scratch state threaded through the repair pipeline stages.

    Each stage function receives the same :class:`_PipelineState` instance,
    mutates ``run`` in place, and reports back whether the pipeline should
    stop by returning ``True``. Splitting the pipeline into per-phase
    functions keeps each stage's own branch, statement, and return count
    small; only ``run_repair_pipeline`` iterates the stage sequence.
    """

    root_dir: Path
    run: RepairRun
    feat: str | None
    dry_run: bool
    include_index: bool
    before: dict[str, Fingerprint]
    current: dict[str, Fingerprint]
    boundary_ns: int | None = None
    initial_checks: list[CheckResult] = field(default_factory=list)

    def refresh_fingerprints(self) -> dict[str, Fingerprint]:
        """Recompute and store the current vault file fingerprints.

        Reuses each file's previously-computed content hash when its
        ``(st_size, st_mtime_ns)`` still matches *and* its mtime is
        strictly older than :attr:`boundary_ns` - the racily-clean rule
        :func:`_vault_file_fingerprints` documents. Only files touched
        since the last capture (or racy relative to the run's start) pay
        the hash cost again.
        """
        self.current = _vault_file_fingerprints(
            self.root_dir, previous=self.current, boundary_ns=self.boundary_ns
        )
        return self.current


def run_repair_pipeline(
    root_dir: Path,
    *,
    dry_run: bool = False,
    include_index: bool = True,
    feature: str | None = None,
) -> RepairRun:
    """Run the vault repair pipeline.

    Args:
        root_dir: Project root directory.
        dry_run: Preview intended changes without mutating files.
        include_index: Rebuild generated feature indexes after fixes.
        feature: Optional feature tag scope, without or with leading ``#``.

    Returns:
        :class:`RepairRun` with per-phase details and postcheck results.
    """
    feat = feature.lstrip("#") if feature else None
    run = RepairRun(dry_run=dry_run, feature=feat, include_index=include_index)
    before = _vault_file_fingerprints(root_dir)
    # Captured once, immediately after the full-hash "before" snapshot and
    # before any stage can mutate a document: every write the pipeline goes
    # on to make happens strictly after this instant, so it is a sound
    # racily-clean boundary for every later refresh in this run (see
    # _vault_file_fingerprints).
    boundary_ns = _repair_boundary_ns(root_dir)
    state = _PipelineState(
        root_dir=root_dir,
        run=run,
        feat=feat,
        dry_run=dry_run,
        include_index=include_index,
        before=before,
        current=before,
        boundary_ns=boundary_ns,
    )

    for stage in _REPAIR_STAGES:
        if stage(state):
            break

    _finalize(run, state.before, state.current)
    return run


def _stage_preflight(state: _PipelineState) -> bool:
    """Check migration status and apply pending migrations. Returns stop."""
    run = state.run
    try:
        status, pending_names = migration_status(state.root_dir)
    except Exception as exc:
        _record_failure(run, RepairPhase.PREFLIGHT, exc)
        run.phases.append(
            {
                "phase": RepairPhase.PREFLIGHT.value,
                "migration_status": "unknown",
                "pending_migrations": [],
                "platform": _platform_summary(state.root_dir),
                "applied_migrations": [],
                "skipped": False,
                "failed": True,
                "error": str(exc),
            }
        )
        return True

    preflight: dict[str, Any] = {
        "phase": RepairPhase.PREFLIGHT.value,
        "migration_status": status.value,
        "pending_migrations": pending_names,
        "platform": _platform_summary(state.root_dir),
        "applied_migrations": [],
        "skipped": False,
    }
    # Computed before the migrations run, which is the only time it can be
    # computed at all: `applied_migrations` is populated afterwards and
    # reports what was removed in the past tense. An operator reaching for
    # "repair" after noticing something wrong is the one most likely to be
    # on a stale manifest, so this is the run with the most pending
    # destructive entries and the one that most needs to say so first.
    doomed = _pending_deletions(state.root_dir)
    if doomed:
        preflight["pending_deletions"] = _deletion_section(state.root_dir, doomed)
        # The journal, not `unresolved`: the later stages rebuild
        # `run.unresolved` from their own check results, so a warning
        # recorded here would survive only on the paths that stop early.
        # The journal is append-only for the whole run.
        _record_journal(
            run,
            RepairPhase.PREFLIGHT,
            action="migration_deletions",
            status="warning",
            message=(
                f"Pending migrations remove {len(doomed)} document(s); copies "
                "are kept under .vault/.trash/. Preview them with "
                "vaultspec-core migrations run --dry-run."
            ),
        )
    if state.dry_run and status == MigrationStatus.PENDING:
        preflight["skipped"] = True
        preflight["message"] = (
            "Dry-run skipped vault scanning because pending migrations would "
            "mutate the workspace on first use."
        )
        run.phases.append(preflight)
        run.postcheck = []
        run.unresolved.append(
            {
                "severity": Severity.WARNING.value,
                "check": RepairPhase.PREFLIGHT.value,
                "message": "Run vaultspec-core migrations run before repair dry-run.",
                "path": None,
            }
        )
        return True

    if not state.dry_run:
        try:
            applied = run_pending_migrations(state.root_dir)
        except Exception as exc:
            _record_failure(run, RepairPhase.PREFLIGHT, exc)
            preflight["failed"] = True
            preflight["error"] = str(exc)
            run.phases.append(preflight)
            state.refresh_fingerprints()
            return True
        if applied:
            state.refresh_fingerprints()
        preflight["applied_migrations"] = [
            {
                "name": result.name,
                "target_version": result.target_version,
                "summary": result.summary,
                "counts": result.counts,
            }
            for result in applied
        ]
        snapshots = [result.snapshot for result in applied if result.snapshot]
        if snapshots:
            preflight["snapshots"] = snapshots
    run.phases.append(preflight)
    return False


def _pending_deletions(root_dir: Path) -> list[Path]:
    """Return every document the pending migrations would delete.

    Never raises: a preview that fails must not turn a repair into an
    error, and the deletions still happen with a snapshot behind them. The
    empty list then means "not known", which
    :func:`_deletion_section` does not have to distinguish because it is
    only called when the list is non-empty.

    Args:
        root_dir: Project root directory.

    Returns:
        The deletion set in execution order, empty when there is none or
        when it could not be computed.
    """
    from ..migrations import preview_deletions

    try:
        return [
            path for preview in preview_deletions(root_dir) for path in preview.paths
        ]
    except Exception:
        logger.exception("Could not preview pending migration deletions")
        return []


def _deletion_section(root_dir: Path, doomed: list[Path]) -> dict[str, Any]:
    """Window *doomed* for the preflight payload.

    Bounded for the same reason every other repair section is: the payload
    grows with how stale the workspace is, and the fold on the measured
    production corpus removes thousands of records.
    """
    paths = [_rel_str(path, root_dir) for path in doomed]
    return windowed_section(paths, limit=_DELETION_PREVIEW_LIMIT)


def _stage_check(state: _PipelineState) -> bool:
    """Run the read-only check pass and stash its results. Returns stop."""
    run = state.run
    try:
        initial = run_all_checks(state.root_dir, feature=state.feat, fix=False)
    except Exception as exc:
        _record_failure(run, RepairPhase.CHECK, exc)
        run.phases.append(_failed_phase(RepairPhase.CHECK, exc))
        return True
    run.phases.append(_checks_phase(RepairPhase.CHECK, initial))
    run.planned_fixes = _collect_fixable(initial)
    run.root_causes = _group_root_causes(initial)
    state.initial_checks = initial
    return False


def _stage_dry_run_finish(state: _PipelineState) -> bool:
    """Report planned fixes and indexes for a dry-run. Returns stop."""
    if not state.dry_run:
        return False

    run = state.run
    root_dir = state.root_dir
    for item in run.planned_fixes:
        _record_journal(
            run,
            RepairPhase.FIX,
            action="planned-fix",
            status="planned",
            path=item.get("path"),
            check=item.get("check"),
            message=item.get("fix_description") or item.get("message"),
        )
    run.phases.append(
        {
            "phase": RepairPhase.FIX.value,
            "dry_run": True,
            "fixed_count": 0,
            "planned_count": len(run.planned_fixes),
            "skipped": False,
        }
    )
    if state.include_index:
        planned_indexes = _index_paths(root_dir, state.feat)
        run.generated_indexes = [_rel_str(p, root_dir) for p in planned_indexes]
        for path in run.generated_indexes:
            _record_journal(
                run,
                RepairPhase.INDEX,
                action="refresh-index",
                status="planned",
                path=path,
            )
        run.phases.append(
            {
                "phase": RepairPhase.INDEX.value,
                "dry_run": True,
                "planned": run.generated_indexes,
                "generated": [],
                "skipped": False,
            }
        )
    else:
        run.phases.append(_skipped_index_phase("disabled by --no-index"))
    run.postcheck = state.initial_checks
    run.phases.append(
        # A dry run writes nothing, so re-running the checkers cannot change
        # what they find: this phase re-reports `state.initial_checks`, the
        # same object the check phase already carried. Measured at 10,476
        # documents the two phases held byte-identical diagnostic sets of 170
        # findings each. Counts stay; the second copy does not.
        _checks_phase(
            RepairPhase.POSTCHECK,
            state.initial_checks,
            dry_run=True,
            include_diagnostics=False,
        )
    )
    run.unresolved = _collect_unresolved(state.initial_checks)
    return True


def _stage_fix(state: _PipelineState) -> bool:
    """Apply fixes, then restamp documents the fix pass rewrote. Returns stop."""
    run = state.run
    root_dir = state.root_dir
    phase_before = state.current
    try:
        fixed = run_all_checks(root_dir, feature=state.feat, fix=True)
    except Exception as exc:
        _record_failure(run, RepairPhase.FIX, exc)
        run.phases.append(_failed_phase(RepairPhase.FIX, exc))
        phase_after = state.refresh_fingerprints()
        _record_file_deltas(run, RepairPhase.FIX, phase_before, phase_after)
        return True
    run.phases.append(_checks_phase(RepairPhase.FIX, fixed))
    phase_after = state.refresh_fingerprints()
    _record_file_deltas(run, RepairPhase.FIX, phase_before, phase_after)

    # Vault-orientation ADR (decision D3): the fix pass rewrote documents,
    # so refresh the modified stamp on exactly those the fix touched. Only
    # files whose fingerprint changed during the fix phase are restamped;
    # untouched documents are left byte-for-byte intact. Re-fingerprint
    # afterwards so the index and postcheck phases observe the restamped
    # state rather than reporting the stamp write as fresh drift.
    rewritten = _changed_files(phase_before, phase_after)
    if _restamp_modified(root_dir, rewritten):
        state.refresh_fingerprints()
    return False


def _stage_index(state: _PipelineState) -> bool:
    """Refresh generated feature indexes after the fix pass. Returns stop."""
    run = state.run
    root_dir = state.root_dir
    if not state.include_index:
        run.phases.append(_skipped_index_phase("disabled by --no-index"))
        return False

    phase_before = state.current
    try:
        generated = _refresh_indexes(root_dir, state.feat)
    except Exception as exc:
        return _handle_index_failure(state, exc, phase_before)

    run.generated_indexes = [_rel_str(path, root_dir) for path in generated]
    run.phases.append(
        {
            "phase": RepairPhase.INDEX.value,
            "dry_run": False,
            "generated": run.generated_indexes,
            "skipped": False,
        }
    )
    phase_after = state.refresh_fingerprints()
    _record_file_deltas(run, RepairPhase.INDEX, phase_before, phase_after)
    return False


def _handle_index_failure(
    state: _PipelineState,
    exc: Exception,
    phase_before: dict[str, Fingerprint],
) -> bool:
    """Record an index-refresh failure and still attempt a postcheck."""
    run = state.run
    _record_failure(run, RepairPhase.INDEX, exc)
    run.phases.append(
        {
            "phase": RepairPhase.INDEX.value,
            "dry_run": False,
            "generated": [],
            "skipped": False,
            "failed": True,
            "error": str(exc),
        }
    )
    phase_after = state.refresh_fingerprints()
    _record_file_deltas(run, RepairPhase.INDEX, phase_before, phase_after)

    failure_unresolved = list(run.unresolved)
    try:
        postcheck = run_all_checks(state.root_dir, feature=state.feat, fix=False)
    except Exception as postcheck_exc:
        _record_failure(run, RepairPhase.POSTCHECK, postcheck_exc)
        run.phases.append(_failed_phase(RepairPhase.POSTCHECK, postcheck_exc))
        return True
    run.postcheck = postcheck
    run.unresolved = failure_unresolved + _collect_unresolved(postcheck)
    run.root_causes = _group_root_causes(postcheck)
    run.phases.append(_checks_phase(RepairPhase.POSTCHECK, postcheck))
    return True


def _stage_postcheck(state: _PipelineState) -> bool:
    """Run the final read-only postcheck pass. Returns stop."""
    run = state.run
    try:
        postcheck = run_all_checks(state.root_dir, feature=state.feat, fix=False)
    except Exception as exc:
        _record_failure(run, RepairPhase.POSTCHECK, exc)
        run.phases.append(_failed_phase(RepairPhase.POSTCHECK, exc))
        return True
    run.postcheck = postcheck
    run.unresolved = _collect_unresolved(postcheck)
    run.root_causes = _group_root_causes(postcheck)
    run.phases.append(_checks_phase(RepairPhase.POSTCHECK, postcheck))
    return False


_REPAIR_STAGES: tuple[Callable[[_PipelineState], bool], ...] = (
    _stage_preflight,
    _stage_check,
    _stage_dry_run_finish,
    _stage_fix,
    _stage_index,
    _stage_postcheck,
)


def _checks_phase(
    phase: RepairPhase,
    results: list[CheckResult],
    *,
    dry_run: bool = False,
    include_diagnostics: bool = True,
) -> dict[str, Any]:
    """Summarise one check pass as a phase entry.

    Args:
        phase: Which pass this is.
        results: The checker results for the pass.
        dry_run: Whether the pass ran without writing.
        include_diagnostics: Whether each checker's findings travel with it.
            Set ``False`` where the findings are provably identical to a phase
            already in the payload; counts are always kept.

    Returns:
        The phase entry.
    """
    return {
        "phase": phase.value,
        "dry_run": dry_run,
        "checks": [
            _result_summary(result, include_diagnostics=include_diagnostics)
            for result in results
        ],
        "error_count": sum(result.error_count for result in results),
        "warning_count": sum(result.warning_count for result in results),
        "info_count": sum(result.info_count for result in results),
        "fixed_count": sum(result.fixed_count for result in results),
    }


def _result_summary(
    result: CheckResult, *, include_diagnostics: bool = True
) -> dict[str, Any]:
    """Summarise one checker's result.

    Args:
        result: The checker's outcome.
        include_diagnostics: Whether the findings travel with the counts.

    Returns:
        The per-checker summary. When findings are omitted, the counts remain
        and ``diagnostics_omitted`` says why, so their absence cannot be read
        as "this checker found nothing".
    """
    summary: dict[str, Any] = {
        "check_name": result.check_name,
        "errors": result.error_count,
        "warnings": result.warning_count,
        "info": result.info_count,
        "fixed_count": result.fixed_count,
        "supports_fix": result.supports_fix,
    }
    if include_diagnostics:
        summary["diagnostics"] = windowed_section(
            [_diagnostic_payload(result.check_name, d) for d in result.diagnostics],
            limit=_NESTED_DIAGNOSTIC_LIMIT,
        )
    else:
        summary["diagnostics_omitted"] = "identical to the check phase"
    return summary


def _diagnostic_payload(check_name: str, diag: CheckDiagnostic) -> dict[str, Any]:
    return {
        "check": check_name,
        "path": str(diag.path) if diag.path is not None else None,
        "message": diag.message,
        "severity": diag.severity.value,
        "fixable": diag.fixable,
        "fix_description": diag.fix_description,
    }


def _failed_phase(phase: RepairPhase, exc: Exception) -> dict[str, Any]:
    return {
        "phase": phase.value,
        "dry_run": False,
        "failed": True,
        "error_count": 1,
        "warning_count": 0,
        "info_count": 0,
        "fixed_count": 0,
        "error": str(exc),
    }


def _record_failure(run: RepairRun, phase: RepairPhase, exc: Exception) -> None:
    run.partial_failure = True
    message = f"{phase.value} phase failed: {exc}"
    run.unresolved.append(
        {
            "severity": Severity.ERROR.value,
            "check": phase.value,
            "message": message,
            "path": None,
            "fixable": False,
            "fix_description": None,
        }
    )
    _record_journal(
        run,
        phase,
        action="phase",
        status="failed",
        message=message,
    )


def _record_journal(
    run: RepairRun,
    phase: RepairPhase,
    *,
    action: str,
    status: str,
    path: str | None = None,
    check: str | None = None,
    message: str | None = None,
) -> None:
    entry: dict[str, Any] = {
        "phase": phase.value,
        "action": action,
        "status": status,
    }
    if path is not None:
        entry["path"] = path
    if check is not None:
        entry["check"] = check
    if message is not None:
        entry["message"] = message
    run.journal.append(entry)


def _collect_fixable(results: Iterable[CheckResult]) -> list[dict[str, Any]]:
    planned: list[dict[str, Any]] = []
    for result in results:
        for diag in result.diagnostics:
            if diag.fixable:
                planned.append(_diagnostic_payload(result.check_name, diag))
    return planned


def _collect_unresolved(results: Iterable[CheckResult]) -> list[dict[str, Any]]:
    unresolved: list[dict[str, Any]] = []
    for result in results:
        for diag in result.diagnostics:
            unresolved.append(_diagnostic_payload(result.check_name, diag))
    return unresolved


#: Diagnostics carried inside a nested payload section.
#:
#: Bounding the *outer* list does not bound the payload: a root-cause bucket
#: is one row that embeds every diagnostic it grouped, and a per-check summary
#: is one row per checker that embeds every finding that checker raised. On a
#: 10,476-document vault with 5% of documents damaged, four root-cause buckets
#: - four rows, none of them elided - carried 837 KB, and six phase entries
#: carried 1.68 MB, together 99% of a 2.5 MB payload. A row cap is not a byte
#: cap wherever a row can contain a collection.
_NESTED_DIAGNOSTIC_LIMIT = 20


def _group_root_causes(results: Iterable[CheckResult]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "structure-and-naming": [],
        "link-integrity": [],
        "generated-index-lifecycle": [],
        "authorial-traceability": [],
        "frontmatter-style": [],
    }
    for result in results:
        for diag in result.diagnostics:
            payload = _diagnostic_payload(result.check_name, diag)
            message = diag.message.lower()
            if result.check_name == "structure" or "case" in message:
                buckets["structure-and-naming"].append(payload)
            elif result.check_name in {"references", "schema"} or any(
                token in message for token in ("adr", "research", "plan")
            ):
                buckets["authorial-traceability"].append(payload)
            elif "index" in message or result.check_name == "features":
                buckets["generated-index-lifecycle"].append(payload)
            elif result.check_name in {"links", "dangling", "body-links", "orphans"}:
                buckets["link-integrity"].append(payload)
            else:
                buckets["frontmatter-style"].append(payload)

    return [
        {
            "root_cause": name,
            "count": len(items),
            "diagnostics": windowed_section(items, limit=_NESTED_DIAGNOSTIC_LIMIT),
        }
        for name, items in buckets.items()
        if items
    ]


def _refresh_indexes(root_dir: Path, feature: str | None) -> list[Path]:
    from ..graph import VaultGraph
    from .index import generate_feature_index_result

    graph = VaultGraph(root_dir)
    features = [feature] if feature else graph.get_features()
    generated: list[Path] = []
    for feat in features:
        result = generate_feature_index_result(root_dir, feat)
        if result.changed:
            generated.append(result.path)
    return generated


def _index_paths(root_dir: Path, feature: str | None) -> list[Path]:
    """Return the feature index paths a repair would rewrite.

    Membership comes from one shared graph, sliced per feature. Omitting
    ``nodes`` here instead would make :func:`generate_feature_index_result`
    rebuild a fresh cache-disabled ``VaultGraph`` - a full parse of every
    document in the vault - once per feature, which is
    ``O(features x documents)``: 130 rebuilds over 1,229 documents measured at
    112.6 s of a 115 s run, and a projected ~72 minutes at 10,476 documents.

    Passing shared nodes is safe on *this* path specifically. The parameter is
    documented as one production callers omit so that membership is re-read
    under the index lock - but the dry-run branch takes ``nullcontext()`` and
    holds no lock, so there is no lock-ordering guarantee to preserve. It
    computes what *would* change and writes nothing. The mutating path is a
    different case and is deliberately left alone here.

    Args:
        root_dir: Project root directory.
        feature: Restrict to one feature, or ``None`` for all.

    Returns:
        The index paths whose canonical content would change.
    """
    from ..graph import VaultGraph
    from .index import generate_feature_index_result

    graph = VaultGraph(root_dir)
    features = [feature] if feature else graph.get_features()
    return [
        result.path
        for feat in features
        if feat
        and (
            result := generate_feature_index_result(
                root_dir, feat, nodes=graph.get_feature_nodes(feat), dry_run=True
            )
        ).changed
    ]


def _skipped_index_phase(reason: str) -> dict[str, Any]:
    return {
        "phase": RepairPhase.INDEX.value,
        "skipped": True,
        "reason": reason,
        "generated": [],
    }


def _record_file_deltas(
    run: RepairRun,
    phase: RepairPhase,
    before: dict[str, Fingerprint],
    after: dict[str, Fingerprint],
) -> None:
    for path in sorted(set(before) | set(after)):
        old = before.get(path)
        new = after.get(path)
        if old == new:
            continue
        if old is None:
            action = "create"
        elif new is None:
            action = "delete"
        else:
            action = "modify"
        _record_journal(
            run,
            phase,
            action=action,
            status="applied",
            path=path,
        )


def _finalize(
    run: RepairRun,
    before: dict[str, Fingerprint],
    after: dict[str, Fingerprint],
) -> None:
    run.changed_files = _changed_files(before, after)
    run.phases.append(
        {
            "phase": RepairPhase.SUMMARY.value,
            "dry_run": run.dry_run,
            "changed_files": run.changed_files,
            "generated_indexes": run.generated_indexes,
            "unresolved_count": len(run.unresolved),
            "partial_failure": run.partial_failure,
            "journal_count": len(run.journal),
            "root_causes": [
                {"root_cause": item["root_cause"], "count": item["count"]}
                for item in run.root_causes
            ],
        }
    )


def _restamp_modified(root_dir: Path, rewritten: Iterable[str]) -> bool:
    """Refresh the modified stamp on documents the fix pass rewrote.

    Implements the repair-pipeline half of the vault-orientation ADR's
    decision D3. For each relative path the fix phase actually changed,
    the document is reloaded, its ``modified:`` frontmatter stamp is
    refreshed to today via the shared
    :func:`vaultspec_core.vaultcore.models.refresh_modified_stamp`
    helper, and the file is rewritten only when the stamp differs from
    what is already on disk. Files that no longer exist (renamed or
    deleted by the fix pass) and non-markdown paths are skipped, and the
    document's line-ending convention is preserved because the helper
    operates on the raw text.

    Each document's reload and rewrite run inside its own per-document
    advisory lock - the sentinel ``execute_edit`` takes - so the stamp this
    pass writes is computed from the bytes it overwrites. Restamping outside
    that lock would let an edit that lands between the read and the write be
    discarded by a replacement derived from the superseded revision: an
    individually-atomic write, no error on either side, and the edit simply
    gone. The lock is taken and released per document rather than held across
    the loop, so a long repair run never freezes the whole corpus.

    Args:
        root_dir: Project root the relative paths resolve against.
        rewritten: Relative POSIX paths the fix phase changed.

    Returns:
        ``True`` when at least one document's stamp was rewritten, so
        the caller knows to re-fingerprint.
    """
    from ..core.helpers import atomic_write
    from .edit_engine import document_write_lock
    from .models import refresh_modified_stamp, vault_today

    today = vault_today()
    changed = False
    for rel in rewritten:
        if not rel.endswith(".md"):
            continue
        path = root_dir / rel
        if not path.is_file():
            continue
        # A case-only rename during the fix phase leaves the old-cased
        # relative path in ``rewritten`` (it vanished from the after-set).
        # On a case-insensitive filesystem ``is_file`` and ``atomic_write``
        # both resolve that stale path to the renamed file and would
        # resurrect the original casing. Confirm the exact name is the one
        # on disk via a case-sensitive parent listing before restamping.
        try:
            if path.name not in {entry.name for entry in path.parent.iterdir()}:
                continue
        except OSError:
            continue
        with document_write_lock(path, root_dir):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            stamped = refresh_modified_stamp(text, today)
            if stamped != text:
                atomic_write(path, stamped)
                changed = True
    return changed


def _vault_file_fingerprints(
    root_dir: Path,
    *,
    previous: dict[str, Fingerprint] | None = None,
    boundary_ns: int | None = None,
) -> dict[str, Fingerprint]:
    """Fingerprint every ``.vault/`` document as ``(size, mtime_ns, sha256)``.

    Size and mtime alone cannot detect every mutation: rewriting the
    fixed-width ``modified: 'yyyy-mm-dd'`` frontmatter stamp - the single
    most common repair-pipeline write - never changes ``st_size``, so a
    same-tick rewrite (ordinary, not pathological, on coarse-grained or
    even NTFS-class filesystems under a fast fix pass) is invisible to
    ``st_mtime_ns`` alone. The content hash closes that gap and matches
    the primitive :mod:`vaultspec_core.graph.cache` already uses.

    Hashing every document on every call is too expensive to pay on each
    of the several fingerprint captures a single repair run makes (a
    ~600ms full pass over this project's own ~1200-document corpus), so
    this follows the same racily-clean reuse rule as
    :func:`vaultspec_core.graph.cache.validate`: when *previous* carries a
    file at the identical ``(size, mtime_ns)`` and that mtime is strictly
    older than *boundary_ns*, the file could not have been rewritten since
    *previous* was captured (mtime quantization is monotonic), so its
    prior hash is reused instead of re-read. Every other file - new,
    size/mtime-changed, or racy - is freshly hashed. The very first call
    in a run (``previous=None``) therefore pays one full-hash pass, and
    every later call in the same run reuses hashes for everything the
    pipeline did not touch.

    Args:
        root_dir: Project root directory.
        previous: The fingerprint mapping from the last capture in this
            run, or ``None`` for the first capture (forces a full hash).
        boundary_ns: A filesystem-quantized instant that predates every
            write this repair run can make (see :func:`_repair_boundary_ns`).
            ``None`` degrades every file to racy - sound, never unsound.

    Returns:
        Mapping of vault-relative POSIX path to :data:`Fingerprint`.
    """
    from ..config import get_config
    from ..graph.cache import hash_file

    docs_dir = root_dir / get_config().docs_dir
    if not docs_dir.is_dir():
        return {}
    fingerprints: dict[str, Fingerprint] = {}
    for path in sorted(docs_dir.rglob("*.md")):
        try:
            rel_parts = path.relative_to(docs_dir).parts
        except ValueError:
            continue
        if any(_is_fingerprint_excluded_dir(part) for part in rel_parts[:-1]):
            continue
        try:
            rel = _rel_str(path, root_dir)
        except ValueError:
            rel = str(path)
        try:
            stat = path.stat()
            size, mtime_ns = stat.st_size, stat.st_mtime_ns
            prior = previous.get(rel) if previous else None
            racy = boundary_ns is None or mtime_ns >= boundary_ns
            if (
                prior is not None
                and not racy
                and (prior[0], prior[1]) == (size, mtime_ns)
            ):
                content_hash = prior[2]
            else:
                content_hash = hash_file(path)
            fingerprints[rel] = (size, mtime_ns, content_hash)
        except OSError:
            continue
    return fingerprints


def _is_fingerprint_excluded_dir(part: str) -> bool:
    return part.startswith(".") or part in _FINGERPRINT_EXCLUDED_DIR_NAMES


def _repair_boundary_ns(root_dir: Path) -> int | None:
    """Return a filesystem-quantized "now", the racily-clean hash boundary.

    Stats a throwaway sentinel file instead of reading the wall clock so
    the boundary passes through the exact same mtime quantization as every
    document mtime it is later compared against - the same reasoning
    :func:`vaultspec_core.graph.cache.validate` applies to a cache file's
    own mtime. On a coarse-grained filesystem an unquantized wall-clock
    reading can floor to a tick *earlier* than a real write that happened
    after it was taken, which would silently defeat the guard; routing
    both sides through an identical stat call cannot.

    Args:
        root_dir: Project root directory to probe alongside.

    Returns:
        The sentinel's ``st_mtime_ns``, or ``None`` when the probe cannot
        be created - callers treat that as "every file is racy", which is
        sound (falls back to always hashing) rather than unsound.
    """
    try:
        probe = tempfile.TemporaryDirectory(
            prefix=".vaultspec-repair-boundary-",
            dir=root_dir,
        )
    except OSError:
        return None
    with probe as probe_dir_name:
        marker = pathlib.Path(probe_dir_name) / "boundary.tmp"
        try:
            marker.write_text("boundary", encoding="utf-8")
            return marker.stat().st_mtime_ns
        except OSError:
            return None


def _changed_files(
    before: dict[str, Fingerprint],
    after: dict[str, Fingerprint],
) -> list[str]:
    paths = sorted(set(before) | set(after))
    return [path for path in paths if before.get(path) != after.get(path)]


def _platform_summary(root_dir: Path) -> dict[str, Any]:
    return {
        "case_sensitive_probe": _case_sensitive_probe(root_dir),
    }


def _case_sensitive_probe(root_dir: Path) -> str:
    try:
        probe = tempfile.TemporaryDirectory(
            prefix=".vaultspec-repair-probe-",
            dir=root_dir,
        )
    except OSError:
        return "unknown"
    with probe as probe_dir_name:
        probe_dir = pathlib.Path(probe_dir_name)
        lower = probe_dir / "case-probe.tmp"
        upper = probe_dir / "CASE-PROBE.tmp"
        try:
            lower.write_text("probe", encoding="utf-8")
            if upper.exists() and lower.resolve() == upper.resolve():
                return "case_insensitive"
            return "case_sensitive" if not upper.exists() else "case_insensitive"
        except OSError:
            return "unknown"


def _rel_str(path: Path, root_dir: Path) -> str:
    try:
        return path.relative_to(root_dir).as_posix()
    except ValueError:
        return path.as_posix()
