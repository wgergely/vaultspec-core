"""Plan and apply the fold of per-Step execution records into one ledger.

Two record shapes predate the ledger:

- ``body-v1`` carries its Step identity in frontmatter and its machine-usable
  content in a ``## Scope`` list the scaffolder filled from the Step row.
  Everything else is prose no consumer reads. A recovered row carries
  :data:`~vaultspec_core.vaultcore.exec_ledger.MIGRATED_OP` (``T``,
  touched) because the schema never recorded an operation, and the prose is
  discarded.
- ``body-v2`` carries a mechanical ``## Changes`` log with real operations,
  an optional ``verify:`` line, and a ``## Notes`` section only on
  exception. Its rows fold with their operations intact and its notes are
  carried into the ledger's ``## Notes`` under the Step id.

A Phase Summary is the union of its Phase's records. It is removed once
every Step of that Phase has rows in the ledger, and left intact otherwise,
so the corpus never loses evidence to the fold. A summary carries no rows
and no notes of its own, so it is also left intact when the fold recovers
nothing: the removal would otherwise destroy a hand-authored narrative on a
run that writes nothing in its place. No file is removed on a code path
where the write meant to preserve its content was skipped.

:func:`plan_fold` only *plans*: it reads nothing and writes nothing, so a dry
run and a real run share one code path and what an operator previews is
what an operator gets. :func:`apply_fold` writes the plan, used by both the
``vault exec fold`` verb and the auto-run migrations so the two cannot drift
into different definitions of the same conversion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .exec_ledger import (
    LEDGER_SUFFIX,
    MIGRATED_OP,
    format_note,
    format_row,
    ledger_step_ids,
    note_lines,
    parse_ledger_rows,
)
from .trash import TrashWriter

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from pathlib import Path

    from .trash import TrashSnapshot

__all__ = [
    "FoldOutcome",
    "FoldPlan",
    "FoldSource",
    "SkippedRecord",
    "apply_fold",
    "collect_sources",
    "phase_steps_of",
    "plan_fold",
    "removals_of",
    "scope_paths",
]

#: A backtick-quoted cell inside a ``## Scope`` list item.
_CELL_RE = re.compile(r"`([^`]*)`")

#: The ``## Scope`` section, up to the next level-two heading.
_SCOPE_RE = re.compile(
    r"^##[ \t]+Scope[ \t]*$(?P<body>.*?)(?=^##[ \t]+|\Z)",
    re.MULTILINE | re.DOTALL,
)

#: A ``## Changes`` heading marks the body-v2 shape.
_CHANGES_HEADING_RE = re.compile(r"^##[ \t]+Changes[ \t]*$", re.MULTILINE)

#: A canonical leaf Step identifier, used to order rows numerically.
_STEP_NUM_RE = re.compile(r"^S(\d+)$")

#: The Phase a summary stem names: ``...-P01-summary`` or ``...-W01-P01-summary``.
_SUMMARY_RE = re.compile(r"-(?:(W\d{2,}[a-z]?)-)?(P\d{2,}[a-z]?)-summary$")


@dataclass(frozen=True)
class FoldSource:
    """One parsed execution record offered to the planner.

    Attributes:
        path: The record's path.
        step_id: Its ``step_id`` frontmatter value, or ``None``.
        body: Its body text, frontmatter already stripped.
    """

    path: Path
    step_id: str | None
    body: str


@dataclass(frozen=True)
class SkippedRecord:
    """One record the planner declined to fold, and why."""

    path: Path
    reason: str


@dataclass
class FoldPlan:
    """The decided outcome of folding one plan's execution records.

    Attributes:
        rows: Ledger ``## Changes`` rows to append, in Step order.
        notes: Ledger ``## Notes`` lines to append, in Step order.
        folded: Records whose content the rows now carry, safe to remove.
        summaries: Phase Summaries whose every Step has rows and whose
            removal is accompanied by a write, safe to remove.
        skipped: Records left untouched, each with a reason.
        recovered_paths: Count of paths carried into rows, summed per record.
    """

    rows: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    folded: list[Path] = field(default_factory=list)
    summaries: list[Path] = field(default_factory=list)
    skipped: list[SkippedRecord] = field(default_factory=list)
    recovered_paths: int = 0

    @property
    def is_empty(self) -> bool:
        """Whether the plan would change nothing on disk."""
        return not self.folded and not self.summaries

    @property
    def recovers_content(self) -> bool:
        """Whether the fold has anything to write in place of what it removes.

        The precondition every removal shares. A fold that recovered no row
        and no note leaves the ledger saying nothing about the records it
        would unlink, so it must unlink none of them - the rule
        :func:`_carries`, the summary retention in :func:`plan_fold`, and
        :func:`removals_of` all state, and which is stated once here so they
        cannot come to disagree.
        """
        return bool(self.rows or self.notes)

    @property
    def removed(self) -> list[Path]:
        """Every record the fold removes: folded records and summaries."""
        return [*self.folded, *self.summaries]


@dataclass(frozen=True)
class FoldOutcome:
    """What a fold wrote and what it backed up first.

    Attributes:
        ledger_path: The ledger the fold wrote, resolved even on a dry run.
        snapshot: The pre-deletion snapshot of every removed record, or
            ``None`` when the fold removed nothing.
    """

    ledger_path: Path
    snapshot: TrashSnapshot | None


def scope_paths(body: str) -> tuple[str, ...]:
    """Return the backticked paths listed in *body*'s ``## Scope`` section.

    Args:
        body: The record body, frontmatter already stripped.

    Returns:
        The scope paths in document order, deduplicated, with empty cells
        dropped. Empty when the record declares no Scope section or the
        section lists no backticked cell.
    """
    match = _SCOPE_RE.search(body)
    if match is None:
        return ()
    seen: dict[str, None] = {}
    for cell in _CELL_RE.findall(match.group("body")):
        value = cell.strip()
        if value:
            seen.setdefault(value, None)
    return tuple(seen)


def _step_sort_key(step_id: str) -> tuple[int, str]:
    """Order Step ids numerically, keeping unparseable ids last but stable."""
    match = _STEP_NUM_RE.match(step_id)
    if match:
        return (int(match.group(1)), "")
    return (10**9, step_id)


def _recover(step_id: str, body: str) -> tuple[list[str], list[str], set[str]]:
    """Return the ``(rows, notes, paths)`` one record contributes.

    A ``body-v2`` record (it has a ``## Changes`` heading) yields its rows
    with their operations intact and its notes re-keyed under *step_id*. A
    ``body-v1`` record yields one ``T`` row per Scope path and no notes. A
    record naming no path still yields a coverage-only row so the Step
    cannot come to read as never executed.
    """
    rows: list[str] = []
    notes: list[str] = []
    paths: set[str] = set()
    has_change_row = False

    if _CHANGES_HEADING_RE.search(body):
        for row in parse_ledger_rows(body):
            if row.op is not None:
                rows.append(format_row(step_id, row.op, *row.paths))
                paths.update(row.paths)
                has_change_row = True
            elif row.label is not None:
                rows.append(format_row(step_id, row.label, *row.paths))
        for keyed, text in note_lines(body):
            notes.append(format_note(keyed or step_id, text))
    else:
        for path in scope_paths(body):
            rows.append(format_row(step_id, MIGRATED_OP, path))
            paths.add(path)
            has_change_row = True

    if not has_change_row:
        # Coverage-only row: the Step was executed and recorded, but the
        # record named no path. Dropping it would lose the mapping.
        rows.insert(0, format_row(step_id, MIGRATED_OP))
    return rows, notes, paths


def _summary_phase(stem: str) -> str | None:
    """Return the display path of the Phase a summary stem names, or ``None``."""
    match = _SUMMARY_RE.search(stem)
    if match is None:
        return None
    wave, phase = match.group(1), match.group(2)
    return f"{wave}.{phase}" if wave else phase


def _carries(ledger_text: str, plan: FoldPlan) -> bool:
    """Whether *ledger_text* demonstrably carries everything *plan* recovered.

    Deletion is gated on this rather than on the write having changed bytes.
    An interrupted fold re-runs with its rows already in the ledger, so a
    byte-change gate would refuse forever and leave the duplication the
    ordering deliberately accepts; a containment gate completes it. A plan
    that recovered nothing carries nothing, so it backs no removal at all.
    """
    if not plan.recovers_content:
        return False
    present = {line.strip() for line in ledger_text.splitlines() if line.strip()}
    return all(line.strip() in present for line in (*plan.rows, *plan.notes))


def plan_fold(
    sources: Iterable[FoldSource],
    *,
    phase_steps: Mapping[str, Sequence[str]] | None = None,
    covered: Iterable[str] = (),
) -> FoldPlan:
    """Decide which records fold into a ledger, and what rows they become.

    A record is skipped rather than folded when folding it would lose
    something the ledger cannot carry:

    - the ledger itself, which is the fold's target, not its input;
    - a record with no ``step_id``, which cannot be attributed to a Step at
      all, so folding it would silently drop its evidence;
    - a Phase Summary whose Phase is unknown to *phase_steps* or whose Steps
      do not all have rows after the fold.

    Args:
        sources: The candidate records.
        phase_steps: Map from a Phase's display path (``P01``, ``W01.P01``)
            and canonical id to its Step ids, from the parent plan. Without
            it no summary is removed.
        covered: Step ids the existing ledger already covers.

    Returns:
        The decided :class:`FoldPlan`.
    """
    plan = FoldPlan()
    foldable: list[tuple[str, Path, str]] = []
    summaries: list[FoldSource] = []

    for source in sources:
        stem = source.path.stem
        if stem.endswith(LEDGER_SUFFIX):
            plan.skipped.append(SkippedRecord(source.path, "is the ledger"))
            continue
        if stem.endswith("-summary"):
            summaries.append(source)
            continue
        if not source.step_id:
            plan.skipped.append(SkippedRecord(source.path, "no step_id"))
            continue
        foldable.append((source.step_id, source.path, source.body))

    foldable.sort(key=lambda item: (_step_sort_key(item[0]), item[1].name))

    folded_ids: set[str] = set()
    for step_id, path, body in foldable:
        rows, notes, paths = _recover(step_id, body)
        plan.rows.extend(rows)
        plan.notes.extend(notes)
        plan.recovered_paths += len(paths)
        folded_ids.add(step_id)
        plan.folded.append(path)

    # A summary contributes no rows and no notes of its own, so a fold that
    # recovers nothing has nothing to write in place of the narrative it
    # would delete. Removing one then destroys hand-authored prose on a run
    # that leaves the ledger byte-identical, so the summary is retained.
    carries_content = plan.recovers_content
    covered_after = set(covered) | folded_ids
    for source in summaries:
        phase = _summary_phase(source.path.stem)
        steps = (phase_steps or {}).get(phase or "")
        if phase is None or steps is None:
            plan.skipped.append(SkippedRecord(source.path, "phase summary"))
        elif not carries_content:
            plan.skipped.append(
                SkippedRecord(source.path, "phase summary; the fold writes nothing")
            )
        elif steps and all(step in covered_after for step in steps):
            plan.summaries.append(source.path)
        else:
            plan.skipped.append(
                SkippedRecord(source.path, "phase summary; Steps not all logged")
            )

    return plan


def summarize(plan: FoldPlan, folder: str) -> str:
    """Render a one-line operator summary of *plan* for *folder*."""
    return (
        f"{folder}: {len(plan.folded)} record(s) -> "
        f"{len(plan.rows)} row(s), {plan.recovered_paths} path(s) recovered, "
        f"{len(plan.summaries)} summary(ies) removed, {len(plan.skipped)} skipped"
    )


def sources_from(
    records: Sequence[tuple[Path, str | None, str]],
) -> tuple[FoldSource, ...]:
    """Build planner inputs from ``(path, step_id, body)`` triples."""
    return tuple(FoldSource(path, step_id, body) for path, step_id, body in records)


def phase_steps_of(plan_path: Path) -> dict[str, list[str]]:
    """Return each Phase's Step ids, keyed by display path and canonical id.

    An unparseable plan yields an empty map, so no summary is removed on its
    account (No-Crash policy: the fold degrades to keeping evidence).
    """
    from ..plan.parser import parse_plan

    try:
        plan = parse_plan(plan_path)
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    mapping: dict[str, list[str]] = {}
    for phase in plan.phases:
        ids = [step.canonical_id for step in phase.steps]
        mapping[phase.display_path] = ids
        mapping.setdefault(phase.canonical_id, ids)
    return mapping


def collect_sources(
    paths: Iterable[Path],
) -> tuple[list[tuple[Path, str | None, str]], str | None, tuple[str, ...]]:
    """Read *paths* into planner triples, the parent plan stem, and ledger coverage.

    Unreadable files are skipped. The plan stem is the first ``-plan`` link
    any record's ``related:`` names. Coverage is the union of Step ids every
    ledger among *paths* already names.
    """
    from .checks.exec_mapping import link_stem
    from .parser import parse_vault_metadata

    records: list[tuple[Path, str | None, str]] = []
    plan_stem: str | None = None
    covered: list[str] = []
    for path in sorted(paths):
        try:
            metadata, body = parse_vault_metadata(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        records.append((path, metadata.step_id, body))
        if path.stem.endswith(LEDGER_SUFFIX):
            covered.extend(ledger_step_ids(body))
        if plan_stem is None:
            for link in metadata.related:
                stem = link_stem(str(link))
                if stem and stem.endswith("-plan"):
                    plan_stem = stem
                    break
    return records, plan_stem, tuple(covered)


def removals_of(plan: FoldPlan, ledger_path: Path | None = None) -> list[Path]:
    """Return exactly the paths :func:`apply_fold` would unlink.

    The single definition of the fold's destruction set, shared by the code
    that deletes and by the code that previews the deletion, so a preview
    cannot describe a different run from the one it precedes.

    The pure half of the removal decision lives here so a preview can apply
    it without a workspace: a plan that recovered nothing has nothing to
    write in place of what it would delete, so it deletes nothing. The other
    half - that the ledger on disk demonstrably carries what was recovered -
    is checked in :func:`apply_fold`, and is true by construction whenever
    its write succeeded, so the two agree on every path that completes.

    Args:
        plan: The decided fold.
        ledger_path: The ledger the fold writes; never itself removed.
            ``None`` from a preview, which has no reason to resolve it.

    Returns:
        The removal set, in plan order.
    """
    if not plan.recovers_content:
        return []
    return [path for path in plan.removed if path != ledger_path]


def apply_fold(
    root_dir: Path,
    plan: FoldPlan,
    *,
    feature: str,
    folder_date: str,
    plan_stem: str,
    dry_run: bool = False,
    trash: TrashWriter | None = None,
) -> FoldOutcome:
    """Write *plan* to the feature's ledger and remove the folded records.

    Records are removed only after the ledger carrying their content is
    durably on disk, so an interruption leaves duplication rather than loss;
    only once that ledger is confirmed to carry every row and note the plan
    recovered; and only after a byte-identical copy of each of them is in
    ``.vault/.trash/``, so an operator who disagrees with the fold can get
    them back whether or not they were committed. A plan that recovered
    nothing removes nothing, and nothing it declines to remove is
    snapshotted: a trash directory holding files that still exist in the
    vault would erode trust in every directory beside it.

    A snapshot that cannot be written raises
    :class:`~vaultspec_core.vaultcore.trash.SnapshotError` here, before the
    first unlink, leaving the ledger written and every record intact: the
    fold then re-runs to the same result rather than deleting unbacked.

    Args:
        root_dir: Project root directory.
        plan: The decided fold.
        feature: The feature tag without ``#``.
        folder_date: The exec folder's date segment (the plan's date).
        plan_stem: The parent plan's stem for the ledger's ``related:``.
        dry_run: Resolve the ledger path without writing or removing.
        trash: Snapshot writer to record the removals in. Pass one to
            collect several folds into a single snapshot directory; the
            default gives this fold its own.

    Returns:
        The :class:`FoldOutcome` naming the ledger and the snapshot.

    Raises:
        SnapshotError: When the removals cannot be snapshotted. Nothing is
            deleted.
    """
    import datetime as _dt

    from ..core.helpers import advisory_lock, atomic_write
    from .exec_ledger import append_notes, append_rows
    from .hydration import (
        DocumentIdentity,
        ExecBinding,
        ParentPlan,
        TemplateFields,
        WritePolicy,
        create_vault_doc,
    )
    from .models import DocType, refresh_modified_stamp
    from .rename_engine import docs_lock_target

    parent = ParentPlan(date=folder_date, stem=plan_stem)
    identity = DocumentIdentity(
        doc_type=DocType.EXEC, feature=feature, date=folder_date
    )
    binding = ExecBinding(plan=parent, ledger=True)
    fields = TemplateFields()

    # Constructing the writer touches nothing: it resolves its directory on
    # the first capture, so a fold that removes nothing leaves no trace. It
    # is bound here so every exit reports the same snapshot state - which
    # for a shared writer is the whole directory, not this fold's share.
    writer = trash if trash is not None else TrashWriter(root_dir, "exec_fold")

    ledger_path = create_vault_doc(
        root_dir,
        identity,
        fields,
        exec_binding=binding,
        write=WritePolicy(force=True, dry_run=True),
    )
    if dry_run or plan.is_empty:
        return FoldOutcome(ledger_path=ledger_path, snapshot=writer.result())

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with advisory_lock(docs_lock_target(ledger_path.parents[2])):
        if not ledger_path.exists():
            create_vault_doc(
                root_dir,
                identity,
                fields,
                exec_binding=binding,
                write=WritePolicy(force=False, dry_run=False),
            )
        text = ledger_path.read_text(encoding="utf-8")
        updated = append_notes(append_rows(text, plan.rows), plan.notes)
        if updated != text:
            atomic_write(ledger_path, refresh_modified_stamp(updated, _dt.date.today()))
        carried = _carries(ledger_path.read_text(encoding="utf-8"), plan)

    # Containment first, snapshot second, unlink last. A record is unlinked
    # only once the ledger is on disk carrying what the fold recovered from
    # it - no file is removed on a path where the write meant to preserve
    # its content was skipped or fell short - and the copy is taken only for
    # records that are then actually removed.
    if not carried:
        return FoldOutcome(ledger_path=ledger_path, snapshot=writer.result())

    # Snapshot outside the docs lock. `advisory_lock` is not reentrant and
    # the writer takes no lock of its own - it owns a directory named for
    # the instant that created it, so there is nothing to serialise.
    removed = removals_of(plan, ledger_path)
    writer.capture(removed)

    for path in removed:
        path.unlink(missing_ok=True)
    return FoldOutcome(ledger_path=ledger_path, snapshot=writer.result())
