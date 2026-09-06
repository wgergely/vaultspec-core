"""Check and optionally fix the CLI-maintained ``modified:`` frontmatter stamp.

Reconciles the ``modified:`` recency stamp introduced by the
vault-orientation ADR (decisions D3 and D3b). The stamp is set equal to
``date:`` at scaffold time and refreshed by every mutating CLI verb, but
the permitted body-prose hand-edit path means a hand-touched document can
drift: the field may be missing, mis-formatted, or attesting a body that
has since changed. This checker is the reconciliation half of that
contract.

Finding semantics (D3b):

- **Missing** ``modified:`` -> finding; the fix adds it, valued from the
  leniently-parsed ``date:`` field, or from the filename's ``yyyy-mm-dd``
  prefix when ``date:`` is absent or itself unparseable.
- **Present but non-canonical yet lenient-parseable** (unquoted scalar,
  ISO timestamp, ``yyyy/mm/dd``, and the other forms
  :func:`~vaultspec_core.vaultcore.models.parse_lenient_date` accepts)
  -> finding; the fix rewrites the field to the canonical quoted
  ``yyyy-mm-dd`` form, preserving the parsed value (never today's date).
- **Unparseable** ``modified:`` -> finding, never auto-fixed and never
  dropped; the message names the offending value so a human can repair it.
- **Stale** (the document's attested ``body_hash:`` disagrees with the
  fingerprint of its live body) -> finding; the fix refreshes the stamp to
  today and re-attests the fingerprint in the same write.
- **Predates** ``date:`` (a canonical, parseable ``modified:`` that is
  strictly earlier than the document's own ``date:``) -> finding; the
  stamp can never legitimately precede the day the document was scaffolded,
  so the fix raises it to ``date:``.

Exactly one finding is produced per document, and staleness outranks the
two value-rewriting repairs below it. Both of those write a historical
value derived from what is already on disk, and every fix re-attests the
fingerprint on its way out, so repairing the form of a stamp on a document
whose body has demonstrably changed would file the new body's fingerprint
beside a pre-edit date and erase the evidence permanently. Today's date
satisfies both repairs anyway: it is canonical by construction and cannot
predate the document's own ``date:``.

Staleness evidence is the content fingerprint, never file mtime. The
modified-stamp-provenance ADR settles why: mtime is a property of the
filesystem event log, and this corpus' own history shows that log being
rewritten wholesale by clones, checkouts, stash/restore cycles, bulk
touches, and - twice - by this checker's own fix path, which stamped a
pre-fix mtime and then rewrote the file, invalidating the value it had
just written. No mtime is consulted anywhere in this module, and there is
no suppression heuristic: once mtime is not evidence, a heuristic to
excuse mtime has no subject.

Convergence follows structurally. The fix writes the comparison's own
right-hand side - stamp plus fingerprint, in one write - so an immediate
second run compares equal and reports clean, which in turn makes the
non-fix run an exact, deterministic preview of what ``--fix`` will do.

Silence, not suspicion. A document carrying no canonical ``body_hash:``
attests nothing about its body and therefore earns no staleness finding,
following the body-schema attestation precedent. Under ``--fix`` such a
document is seeded - the fingerprint is written, the stamp is left exactly
as it stands, and an informational diagnostic records it - so amnesty for
historical stamp values is preserved while correctness restarts from the
seed. A ``body_hash:`` value that is not the canonical
``sha256:<64 hex>`` form was not written by
:mod:`vaultspec_core.vaultcore.body_hash` and cannot be evidence, so it is
treated exactly like an absent one and re-seeded from the live body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...core.helpers import atomic_write
from ..body_hash import body_digest, is_canonical_digest, set_body_hash
from ..models import normalize_date, parse_lenient_date, vault_today
from ._base import (
    CheckDiagnostic,
    CheckResult,
    Severity,
    VaultSnapshot,
    extract_feature_tags,
)

if TYPE_CHECKING:
    import datetime
    from collections.abc import Callable
    from pathlib import Path

    from ..models import DocumentMetadata

__all__ = [
    "check_modified_stamp",
    "filename_date",
    "seed_body_hash",
    "write_stamp",
]

#: Leading ``yyyy-mm-dd`` prefix on a vault filename, the scaffold-time
#: date anchor used when ``date:`` is absent or unparseable.
_FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")

#: Frontmatter ``modified:`` line, capturing leading whitespace so an
#: indented key is rewritten in place rather than duplicated.
_MODIFIED_LINE_RE = re.compile(r"^(?P<indent>[ \t]*)modified:[^\n]*$", re.MULTILINE)

#: Frontmatter ``date:`` line, the insertion anchor when ``modified:`` is
#: absent (the new stamp lands directly after it, matching its layout).
#: The trailing newline is optional so a ``date:`` line that is the last
#: line of the frontmatter block (no ``\n`` before the closing fence,
#: which the fence match strips) still anchors the insertion.
_DATE_LINE_RE = re.compile(
    r"^(?P<indent>[ \t]*)date:[^\n]*(?P<eol>\r\n|\n|$)", re.MULTILINE
)


def filename_date(path: Path) -> str | None:
    """Return the canonical ``yyyy-mm-dd`` filename prefix, or ``None``.

    Args:
        path: Document path whose stem may carry a date prefix.

    Returns:
        The leniently-parsed canonical date string when the filename
        begins with a parseable ``yyyy-mm-dd`` prefix, else ``None``.
    """
    match = _FILENAME_DATE_RE.match(path.name)
    if match is None:
        return None
    return normalize_date(match.group(1))


def _rewrite(
    doc_path: Path,
    transform: Callable[[str], str | None],
    *,
    root_dir: Path | None,
) -> bool:
    """Apply *transform* to *doc_path*'s text and write the result back.

    Centralises the guarded read-modify-write every frontmatter writer in
    this module performs: the per-document advisory lock, the stale-cased-path
    guard, the byte-level read that keeps the source CRLF/LF convention
    observable, and the LF normalisation the transforms operate on.

    Locking is an explicit argument rather than an unconditional acquisition
    because the two callers differ in what already holds a lock. Passing
    *root_dir* takes *doc_path*'s per-document sentinel - the same one
    ``execute_edit`` takes - across the read, the transform, and the write,
    which is what a checker running concurrently with an editing session
    requires. Passing ``None`` runs the cycle unlocked, and is reserved for
    the schema-migration bodies: those already execute inside the migration
    driver's manifest lock, and giving them a docs-domain lock would add a
    manifest-to-document edge to a lock graph whose primitive is
    non-reentrant and has no timeout.

    Args:
        doc_path: Document to rewrite.
        transform: Receives the document's LF-normalised full text and
            returns the replacement text, or ``None`` to decline the write
            (no canonical anchor exists for the field being written).
        root_dir: Project root whose per-document lock guards the cycle, or
            ``None`` to run it unlocked (migration bodies only).

    Returns:
        ``True`` when the file was rewritten, ``False`` otherwise.
    """
    if root_dir is None:
        return _rewrite_locked(doc_path, transform)

    from ..edit_engine import document_write_lock

    with document_write_lock(doc_path, root_dir):
        return _rewrite_locked(doc_path, transform)


def _rewrite_locked(doc_path: Path, transform: Callable[[str], str | None]) -> bool:
    """Run the read-transform-write cycle; the caller owns the locking.

    Args:
        doc_path: Document to rewrite.
        transform: Receives the document's LF-normalised full text and
            returns the replacement text, or ``None`` to decline the write.

    Returns:
        ``True`` when the file was rewritten, ``False`` otherwise.
    """
    # Guard against a stale-cased path from a snapshot built before a
    # sibling checker's case-only rename. On a case-insensitive
    # filesystem ``Path.exists`` and ``open`` both succeed for the wrong
    # casing, and ``atomic_write`` would resurrect the old-cased name. A
    # case-sensitive parent-directory listing check confirms the exact
    # name is the one on disk before we touch it; if it is not, the write
    # is skipped and the next clean pass reaches the correctly-cased file.
    try:
        if doc_path.name not in {entry.name for entry in doc_path.parent.iterdir()}:
            return False
    except OSError:
        return False

    try:
        content = doc_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    source_newline = "\r\n" if "\r\n" in content else "\n"
    new_text = transform(content.replace("\r\n", "\n"))
    if new_text is None:
        return False

    rendered = (
        new_text if source_newline == "\n" else new_text.replace("\n", source_newline)
    )
    atomic_write(doc_path, rendered)
    return True


def _stamp_frontmatter(text: str, value: str) -> str | None:
    """Return *text* with its ``modified:`` field set to *value*.

    Operates on LF-normalised full document text and preserves every other
    character. When the field already exists its value is rewritten
    (keeping indentation); when absent it is inserted directly after the
    ``date:`` line.

    Args:
        text: LF-normalised full document text.
        value: Canonical ``yyyy-mm-dd`` date string to stamp.

    Returns:
        The rewritten text, or ``None`` when the document has no
        frontmatter fence, or carries neither ``modified:`` nor a
        ``date:`` anchor to insert after.
    """
    fence = re.match(r"^(﻿?)---[ \t]*\n(.*?)\n---", text, re.DOTALL)
    if not fence:
        return None

    block_start = fence.start(2)
    block_end = fence.end(2)
    frontmatter = text[block_start:block_end]
    canonical = f"'{value}'"

    existing = _MODIFIED_LINE_RE.search(frontmatter)
    if existing is not None:
        indent = existing.group("indent")
        replacement = f"{indent}modified: {canonical}"
        new_frontmatter = (
            frontmatter[: existing.start()]
            + replacement
            + frontmatter[existing.end() :]
        )
        return text[:block_start] + new_frontmatter + text[block_end:]

    date_line = _DATE_LINE_RE.search(frontmatter)
    if date_line is None:
        return None
    indent = date_line.group("indent")
    insert_at = block_start + date_line.end()
    if date_line.group("eol"):
        # Date line carries its own newline: drop the new stamp on the
        # following line, terminated so the next line is undisturbed.
        stamp_line = f"{indent}modified: {canonical}\n"
    else:
        # Date line is the last line of the block (its newline was
        # consumed by the closing-fence match): open a new line first.
        stamp_line = f"\n{indent}modified: {canonical}"
    return text[:insert_at] + stamp_line + text[insert_at:]


def write_stamp(doc_path: Path, value: str, *, root_dir: Path | None) -> bool:
    """Set the ``modified:`` stamp to *value* and re-attest ``body_hash:``.

    Both fields move in one write, which is what makes the staleness fix
    converge: the value the next run compares against is written by the
    same operation that resolves the finding. A document with no
    frontmatter fence, or one missing both ``modified:`` and ``date:``, is
    left untouched (no canonical anchor exists). The source CRLF/LF
    convention and every other byte are preserved.

    Args:
        doc_path: Document to rewrite.
        value: Canonical ``yyyy-mm-dd`` date string to stamp.
        root_dir: Project root whose per-document advisory lock serialises
            the read-modify-write against a concurrent editor, or ``None``
            to run it unlocked. See :func:`_rewrite` for which callers may
            pass ``None`` and why.

    Returns:
        ``True`` when the file was rewritten, ``False`` otherwise.
    """

    def transform(text: str) -> str | None:
        stamped = _stamp_frontmatter(text, value)
        if stamped is None:
            return None
        return set_body_hash(stamped)

    return _rewrite(doc_path, transform, root_dir=root_dir)


def seed_body_hash(doc_path: Path, *, root_dir: Path | None) -> bool:
    """Attest *doc_path*'s current body without touching its ``modified:``.

    The amnesty half of the modified-stamp-provenance decision: a document
    that has never been fingerprinted is seeded with the verifiable fact of
    what its body is today, while its historical stamp value - which may
    carry inherited inaccuracy no available source can improve on - stands
    exactly as it is. Correctness restarts from the seed rather than from a
    third generation of inferred dates.

    Args:
        doc_path: Document to seed.
        root_dir: Project root whose per-document advisory lock serialises
            the read-modify-write against a concurrent editor, or ``None``
            to run it unlocked. See :func:`_rewrite` for which callers may
            pass ``None`` and why.

    Returns:
        ``True`` when the file was rewritten, ``False`` when it could not
        be read, or its frontmatter offers no canonical anchor for the
        field.
    """

    def transform(text: str) -> str | None:
        seeded = set_body_hash(text)
        return None if seeded == text else seeded

    return _rewrite(doc_path, transform, root_dir=root_dir)


@dataclass(frozen=True)
class _Finding:
    """One reconciliation finding, before it is reported or applied.

    Every branch of the checker resolves to this single shape, so the
    report-vs-fix decision lives in one place (:func:`_emit`) rather than
    being re-spelled per branch.

    Attributes:
        message: Reported when the stamp is left as it stands.
        severity: Severity carried by that report.
        stamp: Canonical value ``--fix`` writes, or ``None`` when the
            finding can never be auto-fixed - an unparseable value, or a
            missing stamp with no ``date:``/filename anchor to backfill
            from. ``None`` is also what makes the report unfixable.
        fixed_message: Reported instead when ``--fix`` writes the stamp.
        fix_description: Corrective action named on the unfixed report.

    Note:
        ``fixed_message`` and ``fix_description`` are read only when
        ``stamp`` is not ``None``, so a builder may leave them at their
        defaults - or interpolate an absent stamp into them - whenever it
        yields ``stamp=None``.
    """

    message: str
    severity: Severity
    stamp: str | None
    fixed_message: str = ""
    fix_description: str | None = None


def _missing_finding(doc_path: Path, metadata: DocumentMetadata) -> _Finding:
    """Build the finding for an absent ``modified:`` field."""
    backfill = normalize_date(metadata.date) or filename_date(doc_path)
    return _Finding(
        message="Missing modified stamp.",
        severity=Severity.WARNING,
        stamp=backfill,
        fixed_message=f"Added modified stamp '{backfill}'.",
        fix_description=f"add modified: '{backfill}'",
    )


def _unparseable_finding(raw_modified: str) -> _Finding:
    """Build the finding for a ``modified:`` value no parser accepts."""
    return _Finding(
        message=(
            f"Unparseable modified stamp '{raw_modified}'; "
            "cannot auto-fix - repair the value by hand."
        ),
        severity=Severity.ERROR,
        stamp=None,
    )


def _noncanonical_finding(raw_modified: str, canonical: str) -> _Finding:
    """Build the finding for a parseable but non-canonical ``modified:``."""
    return _Finding(
        message=(
            f"Non-canonical modified stamp '{raw_modified}'; "
            f"canonical form is '{canonical}'."
        ),
        severity=Severity.WARNING,
        stamp=canonical,
        fixed_message=(f"Normalized modified stamp '{raw_modified}' -> '{canonical}'."),
        fix_description=f"rewrite to '{canonical}'",
    )


def _predates_finding(canonical: str, date_parsed: datetime.date) -> _Finding:
    """Build the finding for a stamp older than the document's ``date:``."""
    floor_value = date_parsed.isoformat()
    return _Finding(
        message=(
            f"Modified stamp '{canonical}' predates its own "
            f"date '{floor_value}'; a stamp cannot be older "
            "than the document it stamps."
        ),
        severity=Severity.WARNING,
        stamp=floor_value,
        fixed_message=(
            f"Modified stamp '{canonical}' predated date "
            f"'{floor_value}'; raised to '{floor_value}'."
        ),
        fix_description=f"raise to '{floor_value}'",
    )


def _stale_finding(raw_modified: str, today: datetime.date) -> _Finding:
    """Build the finding for a body that has outrun its attested fingerprint.

    The fix stamps *today* - the observation date - because it is the only
    honest value available: the true date of an unstamped hand edit is
    unrecorded, and today is its upper bound. The stamp's meaning for such
    a document is therefore "reconciled on", one day coarser in truth than
    for a CLI-mutated one.
    """
    stale_value = today.isoformat()
    return _Finding(
        message=(
            f"Stale modified stamp '{raw_modified}'; the document body no longer "
            "matches its attested fingerprint (unstamped edit)."
        ),
        severity=Severity.WARNING,
        stamp=stale_value,
        fixed_message=(
            f"Refreshed stale modified stamp '{raw_modified}' -> '{stale_value}' "
            "and re-attested the body fingerprint."
        ),
        fix_description=f"refresh to '{stale_value}' and re-attest the body",
    )


def _classify(
    doc_path: Path,
    metadata: DocumentMetadata,
    *,
    body: str,
    today: datetime.date,
) -> _Finding | None:
    """Return the single finding *doc_path* earns, or ``None`` when clean.

    The branches are ordered by how much they know: each one is only
    reached once the cheaper diagnoses above it have been ruled out, so
    exactly one finding is ever produced per document.

    Args:
        doc_path: Document being reconciled.
        metadata: Its parsed frontmatter.
        body: Its live body text, from the shared vault snapshot.
        today: The vault's current date, stamped on a staleness fix.

    Returns:
        The finding, or ``None`` when the stamp is canonical, no earlier
        than ``date:``, and attesting the body the document actually
        carries - or when the document attests nothing at all, which is
        silence rather than a finding.
    """
    raw_modified = metadata.modified
    if not raw_modified:
        return _missing_finding(doc_path, metadata)

    parsed = parse_lenient_date(raw_modified)
    if parsed is None:
        return _unparseable_finding(raw_modified)

    # Staleness outranks the two repairs below it, which both rewrite the
    # stamp to a historical value derived from what is already on disk. Every
    # fix re-attests the fingerprint on its way out, so repairing the form
    # first would write the new body's fingerprint beside a date that predates
    # the edit - erasing the only evidence that the edit happened, silently
    # and permanently. Today's date subsumes both repairs anyway: it is
    # canonical by construction and cannot predate the document's own date:.
    attested = metadata.body_hash
    if is_canonical_digest(attested) and attested != body_digest(body):
        return _stale_finding(raw_modified, today)

    # Non-canonical-but-parseable: the stored value is not the bare
    # canonical string (e.g. an ISO timestamp or yyyy/mm/dd).
    canonical = parsed.isoformat()
    if raw_modified != canonical:
        return _noncanonical_finding(raw_modified, canonical)

    # Semantic floor: modified: must never predate date: (D3b's own
    # invariant - the stamp starts equal to date: at scaffold and only
    # ever moves forward). A value already earlier than date:, whether
    # hand-entered or inherited from a pre-canonicalization edit, would
    # otherwise sail through the canonical-format and staleness checks
    # looking clean forever: staleness only compares the body against its
    # own attestation, never against date:, so this is the only place
    # that invariant is enforced. Reached only when the body still matches
    # its attestation, so raising the stamp here re-attests an unchanged
    # fingerprint and the run converges.
    date_parsed = parse_lenient_date(metadata.date)
    if date_parsed is not None and parsed < date_parsed:
        return _predates_finding(canonical, date_parsed)

    return None


def _emit(
    result: CheckResult,
    finding: _Finding,
    *,
    doc_path: Path,
    root_dir: Path,
    rel_path: Path,
    fix: bool,
) -> bool:
    """Record *finding* on *result*, applying it first when asked to.

    Under ``fix`` an auto-fixable finding is written to disk and reported
    as an informational repair; a finding that is not auto-fixable, or one
    whose write is refused (no ``date:`` anchor, a stale-cased path), falls
    through to the unfixed report so it is never silently dropped.

    Returns:
        ``True`` when the finding was applied to disk, ``False`` when it
        was reported unfixed.
    """
    if (
        fix
        and finding.stamp is not None
        and write_stamp(doc_path, finding.stamp, root_dir=root_dir)
    ):
        result.fixed_count += 1
        result.diagnostics.append(
            CheckDiagnostic(
                path=rel_path,
                message=finding.fixed_message,
                severity=Severity.INFO,
            )
        )
        return True

    fixable = finding.stamp is not None
    result.diagnostics.append(
        CheckDiagnostic(
            path=rel_path,
            message=finding.message,
            severity=finding.severity,
            fixable=fixable,
            fix_description=finding.fix_description if fixable else None,
        )
    )
    return False


def _scoped_docs(
    snapshot: VaultSnapshot, feature: str | None
) -> list[tuple[Path, DocumentMetadata, str]]:
    """Return the ``(path, metadata, body)`` triples in scope for this run."""
    if not feature:
        return [
            (doc_path, metadata, body)
            for doc_path, (metadata, body) in snapshot.items()
        ]
    feat = feature.lstrip("#")
    return [
        (doc_path, metadata, body)
        for doc_path, (metadata, body) in snapshot.items()
        if feat in extract_feature_tags(metadata.tags)
    ]


def check_modified_stamp(
    root_dir: Path,
    *,
    snapshot: VaultSnapshot,
    feature: str | None = None,
    fix: bool = False,
) -> CheckResult:
    """Validate and reconcile the ``modified:`` recency stamp on every document.

    Implements the reconciliation half of the vault-orientation ADR
    (decisions D3, D3b) on the evidence source the
    modified-stamp-provenance ADR settled. For each scanned document the
    checker reports a finding when the ``modified:`` stamp is missing,
    present but non-canonical, unparseable, earlier than the document's own
    ``date:``, or stale - meaning the document's attested ``body_hash:``
    disagrees with the fingerprint of the body it now carries. Under
    ``fix`` it adds, normalizes, raises, or refreshes the stamp as the
    module docstring describes, always re-attesting the fingerprint in the
    same write. The unparseable case is reported but never rewritten so a
    hand-entered value is never silently lost.

    A document that attests no fingerprint earns no staleness finding.
    Under ``fix`` it is seeded instead: the fingerprint is written from the
    live body, the stamp is left untouched, and an informational diagnostic
    records the seed.

    File mtime is not consulted. See the module docstring for why, and for
    the convergence property that follows from fixing stamp and
    fingerprint together.

    Args:
        root_dir: Project root directory.
        snapshot: Pre-built snapshot mapping document paths to parsed
            ``(metadata, body)`` tuples. The body is the live text the
            fingerprint is computed from, so in the ``--fix`` pipeline this
            snapshot must post-date every checker that rewrites bodies.
        feature: Restrict checks to documents carrying this feature tag
            (without ``#``).
        fix: When ``True``, add missing stamps, normalize non-canonical
            ones, refresh stale ones, and seed un-attested documents;
            unparseable values are reported but left untouched.

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with
        check name ``"modified-stamp"``.
    """
    result = CheckResult(check_name="modified-stamp", supports_fix=True)
    today = vault_today()

    for doc_path, metadata, body in _scoped_docs(snapshot, feature):
        rel_path = doc_path.relative_to(root_dir)
        finding = _classify(doc_path, metadata, body=body, today=today)
        applied = False
        if finding is not None:
            applied = _emit(
                result,
                finding,
                doc_path=doc_path,
                root_dir=root_dir,
                rel_path=rel_path,
                fix=fix,
            )

        # Seeding runs only when no fix already wrote this document: every
        # stamp write re-attests the fingerprint on its way out, so a second
        # write here would be redundant. A finding reported unfixed (an
        # unparseable value, a missing stamp with no anchor) is still seeded:
        # the fingerprint is a fact about the body and is independent of
        # whatever is wrong with the stamp.
        if (
            fix
            and not applied
            and not is_canonical_digest(metadata.body_hash)
            and seed_body_hash(doc_path, root_dir=root_dir)
        ):
            result.fixed_count += 1
            result.diagnostics.append(
                CheckDiagnostic(
                    path=rel_path,
                    message=(
                        "Seeded body fingerprint; the modified stamp is left "
                        "as it stands and staleness is tracked from here."
                    ),
                    severity=Severity.INFO,
                )
            )

    return result
