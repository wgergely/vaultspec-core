"""Append one Step's evidence to its plan's execution ledger.

This is the single write path for execution evidence. The CLI verb
``vault exec log`` and the MCP ``log`` tool both call :func:`log_step`, so
the two surfaces cannot drift on what a ledger row is or where it lands.

The writer never infers an operation from disk state: an executor knows what
it did, and guessing would record evidence nobody produced. It creates the
ledger on first use, appends thereafter, and serialises concurrent appends
to one ledger through the shared advisory lock.
"""

from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..core.exceptions import VaultSpecError
from .exec_ledger import (
    BY_LABEL,
    VERIFY_LABEL,
    append_notes,
    append_rows,
    format_note,
    format_row,
)

if TYPE_CHECKING:
    from pathlib import Path

    from .query_listing import VaultDocument

logger = logging.getLogger(__name__)

__all__ = [
    "ExecLogError",
    "LogOutcome",
    "LogRequest",
    "log_step",
    "parse_row_spec",
    "parse_verify_spec",
]

#: The change operations ``--row`` accepts. ``T`` is reserved for the fold.
_ROW_OPS = frozenset({"A", "M", "D", "R"})

#: The results a ``verify:`` row may carry.
_VERIFY_RESULTS = frozenset({"pass", "fail"})


class ExecLogError(VaultSpecError):
    """Raised when a log request cannot be honoured as written."""


@dataclass(frozen=True)
class LogRequest:
    """One Step's evidence to append.

    Attributes:
        feature: Feature tag, with or without a leading ``#``.
        plan_stem: Stem of the parent plan the ledger records.
        step: Canonical Step id or display path being logged.
        rows: Parsed ``(op, paths)`` pairs from :func:`parse_row_spec`.
        verify: ``(command, result)`` for a ``verify:`` row, or ``None``.
        by: The persona for a ``by:`` row, or ``None``.
        notes: Exception notes, one ``## Notes`` line each.
    """

    feature: str
    plan_stem: str
    step: str
    rows: tuple[tuple[str, tuple[str, ...]], ...] = ()
    verify: tuple[str, str] | None = None
    by: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class LogOutcome:
    """What :func:`log_step` wrote.

    Attributes:
        path: The ledger's path.
        step_id: The canonical Step id the rows were logged under.
        rows: The rendered ``## Changes`` rows offered for append.
        notes: The rendered ``## Notes`` lines offered for append.
        changed: Whether the ledger's text changed (``False`` on an
            idempotent re-log or a dry run).
        created: Whether the ledger was created by this call.
    """

    path: Path
    step_id: str
    rows: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)
    changed: bool = False
    created: bool = False


def parse_row_spec(spec: str) -> tuple[str, tuple[str, ...]]:
    """Parse one ``OP:path`` or ``R:old->new`` row spec.

    Args:
        spec: The raw ``--row`` value.

    Returns:
        The ``(op, paths)`` pair.

    Raises:
        ExecLogError: On a malformed spec, an unknown operation, or a rename
            missing one of its two paths.
    """
    op, separator, remainder = spec.partition(":")
    op = op.strip().upper()
    if not separator or not remainder.strip():
        raise ExecLogError(f"invalid --row {spec!r}: expected 'OP:path'")
    if op not in _ROW_OPS:
        raise ExecLogError(
            f"invalid --row {spec!r}: unknown operation {op!r}; use A, M, D, or R"
        )
    if op == "R":
        old, arrow, new = remainder.partition("->")
        if not arrow or not old.strip() or not new.strip():
            raise ExecLogError(f"invalid --row {spec!r}: a rename needs 'R:old->new'")
        return op, (old.strip(), new.strip())
    return op, (remainder.strip(),)


def parse_verify_spec(spec: str) -> tuple[str, str]:
    """Parse one ``<command>=pass|fail`` verify spec.

    The result is taken after the last ``=`` so a command carrying ``=`` in
    its own arguments still parses.

    Args:
        spec: The raw ``--verify`` value.

    Returns:
        The ``(command, result)`` pair.

    Raises:
        ExecLogError: When the spec has no result or the result is not
            ``pass`` or ``fail``.
    """
    command, separator, result = spec.rpartition("=")
    result = result.strip().lower()
    if not separator or not command.strip() or result not in _VERIFY_RESULTS:
        raise ExecLogError(
            f"invalid --verify {spec!r}: expected '<command>=pass' or '<command>=fail'"
        )
    return command.strip(), result


def _resolve_plan_date(plan_doc: VaultDocument) -> str:
    """Return the plan's date as a canonical token for naming its ledger.

    The ledger's folder and its filename are both named from the parent
    plan's date, and that date is document content - a plan obtained with a
    repository decides those two path segments. It is therefore admitted as
    a calendar date and re-rendered from the parse, so what reaches the
    composition is digits and hyphens whatever the file said.

    An unusable stamp falls back to the ``yyyy-mm-dd`` prefix of the plan's
    own filename rather than failing the command. Every vault document's
    name begins with its date by schema, so the fallback is available in
    practice, and it is the same substitution the document lister already
    makes for a plan carrying no ``date:`` at all - extending it from a
    missing stamp to an unusable one keeps a workspace with one bad
    frontmatter line working instead of blocking execution logging on it.
    The fallback is announced, and it is admitted through the same parse, so
    it can no more steer a path than the frontmatter value could.

    Args:
        plan_doc: The parent plan the ledger records.

    Returns:
        A canonical ``yyyy-mm-dd`` string.

    Raises:
        ExecLogError: When neither the frontmatter stamp nor the filename
            prefix is a calendar date, leaving nothing to name the ledger.
    """
    from .normalize import normalize_vault_date

    stated = normalize_vault_date(plan_doc.date, label="plan date")
    if stated.ok and stated.value is not None:
        return stated.value

    from_name = normalize_vault_date(plan_doc.path.stem[:10], label="plan date")
    if from_name.ok and from_name.value is not None:
        logger.warning(
            "Plan '%s' carries an unusable date: %s Naming this ledger from "
            "the plan's filename date '%s' instead; correct the plan's "
            "`date:` frontmatter to silence this.",
            plan_doc.path.name,
            stated.error,
            from_name.value,
        )
        return from_name.value

    raise ExecLogError(
        f"Plan '{plan_doc.path.name}' has no usable date: {stated.error} "
        "Its filename carries no `yyyy-mm-dd` prefix to fall back on, so "
        "there is nothing to name the ledger from. Set the plan's `date:` "
        "frontmatter to its calendar date before logging execution."
    )


def log_step(
    root_dir: Path, request: LogRequest, *, dry_run: bool = False
) -> LogOutcome:
    """Append *request*'s evidence to its plan's ledger, creating it on first use.

    Args:
        root_dir: Project root directory.
        request: The Step's evidence.
        dry_run: Resolve the target and render the rows without writing.

    Returns:
        The :class:`LogOutcome`.

    Raises:
        ExecLogError: When the feature, plan, or Step does not resolve, or
            the ledger on disk carries no ``## Changes`` section.
    """
    from ..core.helpers import advisory_lock, atomic_write
    from ..plan.commands.step_ops import (
        AmbiguousStepError,
        StepNotFoundError,
        find_step,
    )
    from ..plan.parser import parse_plan
    from .hydration import (
        DocumentIdentity,
        ExecBinding,
        ParentPlan,
        TemplateFields,
        WritePolicy,
        create_vault_doc,
    )
    from .models import DocType, refresh_modified_stamp
    from .normalize import normalize_feature_tag
    from .query import list_documents
    from .rename_engine import docs_lock_target

    norm = normalize_feature_tag(request.feature)
    if not norm.ok or norm.value is None:
        raise ExecLogError(str(norm.error))
    feature = norm.value

    plan_doc = next(
        (
            doc
            for doc in list_documents(root_dir, doc_type="plan")
            if doc.path.stem == request.plan_stem
        ),
        None,
    )
    if plan_doc is None:
        raise ExecLogError(
            f"No plan found for feature '{feature}' with stem "
            f"'{request.plan_stem}'. Create a plan document before logging execution."
        )
    try:
        target_step = find_step(parse_plan(plan_doc.path), request.step)
    except (StepNotFoundError, AmbiguousStepError) as exc:
        raise ExecLogError(str(exc)) from exc

    plan = ParentPlan(date=_resolve_plan_date(plan_doc), stem=plan_doc.path.stem)
    identity = DocumentIdentity(
        doc_type=DocType.EXEC, feature=feature, date=plan.date or ""
    )
    binding = ExecBinding(plan=plan, ledger=True)
    fields = TemplateFields()
    step_id = target_step.canonical_id

    rendered = [format_row(step_id, op, *paths) for op, paths in request.rows]
    if request.verify is not None:
        rendered.append(format_row(step_id, VERIFY_LABEL, *request.verify))
    if request.by:
        rendered.append(format_row(step_id, BY_LABEL, request.by.strip()))
    notes = [format_note(step_id, text) for text in request.notes if text.strip()]

    # Resolve the path without writing so an existing ledger is appended to,
    # never overwritten - a rewrite would discard other Steps' history.
    ledger_path = create_vault_doc(
        root_dir,
        identity,
        fields,
        exec_binding=binding,
        write=WritePolicy(force=True, dry_run=True),
    )
    if dry_run:
        return LogOutcome(
            ledger_path, step_id, tuple(rendered), tuple(notes), created=False
        )

    # Two workers closing different Steps of one plan append to one file; the
    # docs-domain lock (the sentinel every `.vault` mutator shares, under the
    # gitignored `data/` subtree) serialises the read-modify-write so neither
    # append is lost. `.vault/exec/<folder>/<ledger>` sits two levels below
    # the docs directory.
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with advisory_lock(docs_lock_target(ledger_path.parents[2])):
        created = not ledger_path.exists()
        if created:
            create_vault_doc(
                root_dir,
                identity,
                fields,
                exec_binding=binding,
                write=WritePolicy(force=False, dry_run=False),
            )

        text = ledger_path.read_text(encoding="utf-8")
        # Appended against the whole document, not a split-off body:
        # frontmatter is YAML and can never carry a '## Changes' heading, so
        # the section match is unambiguous.
        try:
            updated = append_rows(text, rendered) if rendered else text
        except ValueError as exc:
            raise ExecLogError(str(exc)) from exc
        updated = append_notes(updated, notes)

        changed = updated != text
        if changed:
            atomic_write(ledger_path, refresh_modified_stamp(updated, _dt.date.today()))

    return LogOutcome(
        ledger_path, step_id, tuple(rendered), tuple(notes), changed, created
    )
