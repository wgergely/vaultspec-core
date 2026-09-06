"""Typer-free body/frontmatter edit engine over a vault document.

This module is the shared core behind the ``vault set-body`` /
``vault set-frontmatter`` / ``vault edit`` CLI verbs and the MCP ``edit``
tool.  It owns the whole resolve -> concurrency-guard -> compose -> validate
-> write pipeline and returns a typed :class:`EditResult`; it renders no
console output, imports no Typer, and never raises :class:`typer.Exit`.

The engine sits at the same layer as the other ``vaultcore`` cores
(:mod:`vaultspec_core.vaultcore.hydration`,
:mod:`vaultspec_core.vaultcore.orientation`): it takes a ``root_dir`` plus
plain data, returns a dataclass, and raises the typed :class:`EditError`
from its lower helpers.  The public entry point :func:`execute_edit` folds
every reachable failure into an ``EditResult`` with ``status == "failed"``
and a structured ``error`` payload, so a caller never needs a ``try`` block
around it - the per-item failure model the MCP batch surface consumes.

Every path composes existing core machinery and writes NO new validation
logic: frontmatter conformance is :meth:`DocumentMetadata.validate`, and
body/link conformance is the shipped ``frontmatter`` / ``links`` /
``body-links`` checkers run over an in-memory single-document snapshot of
the *proposed* content - so the refuse-on-error decision is made strictly
before any byte is persisted.  Optimistic concurrency is the git blob OID
(:func:`~vaultspec_core.vaultcore.blob_hash.git_blob_oid`) of the pre-write
on-disk bytes, byte-compatible with the dashboard engine's hash.

Canonical statuses (:attr:`EditResult.status`): ``updated`` (content
changed), ``unchanged`` (a no-op or a dry-run), ``failed`` (conflict,
validation refusal, resolution failure, or write error).
"""

from __future__ import annotations

import dataclasses
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from vaultspec_core.vaultcore.checks._base import CheckDiagnostic
    from vaultspec_core.vaultcore.models import DocumentMetadata

__all__ = [
    "EditError",
    "EditResult",
    "document_lock_target",
    "document_write_lock",
    "enforce_blob_hash",
    "execute_edit",
    "invalidate_graph_cache",
    "resolve_document_path",
    "validate_proposed",
]


class EditError(Exception):
    """A pipeline-level failure carrying a structured ``data`` payload.

    Raised by the lower helpers to unwind to :func:`execute_edit`, which
    folds it into an :class:`EditResult` with ``status == "failed"``.  The
    payload is merged into ``data`` so a helper can attach ``conflict``,
    ``refused``, ``checks``, or ``errors`` without re-deriving the failed
    shape.

    Args:
        message: A human-readable failure summary.
        data: The structured payload merged into the failed result's
            ``error`` mapping (e.g. ``conflict`` / ``expected`` / ``actual``
            for a blob-hash conflict, or ``path`` for a resolution failure).
    """

    def __init__(self, message: str, data: dict[str, object]) -> None:
        self.message = message
        self.data = data
        super().__init__(message)


@dataclass(frozen=True)
class EditResult:
    """The typed outcome of one :func:`execute_edit` call.

    Attributes:
        status: The canonical outcome word - ``updated``, ``unchanged``, or
            ``failed``.
        path: The absolute backing-file path as a string, or the raw
            reference when resolution failed before a path was known.
        blob_hash: The git blob OID of the post-write (or, in ``dry_run``,
            the would-be) bytes on success; ``None`` on failure.
        checks: The rendered conformance diagnostics gathered pre-write.
        error: The structured failure payload on ``failed`` (carrying
            ``message`` plus any of ``conflict`` / ``refused`` / ``checks`` /
            ``errors`` / ``expected`` / ``actual`` / ``path``); ``None`` on
            success.
        warnings: The messages of WARNING-severity diagnostics, surfaced
            separately from the blocking ``checks`` errors for callers that
            report advisories per item.
        dry_run: ``True`` when the write was previewed, not performed.
        changed: On a ``dry_run`` preview, whether the proposed bytes differ
            from the on-disk bytes; ``None`` otherwise.
    """

    status: str
    path: str | None = None
    blob_hash: str | None = None
    checks: list[dict[str, object]] = field(default_factory=list)
    error: dict[str, object] | None = None
    warnings: list[str] = field(default_factory=list)
    dry_run: bool = False
    changed: bool | None = None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_document_path(ref: str, root_dir: Path) -> Path:
    """Resolve a stem, filename, or path reference to an on-disk document.

    Mirrors how ``vault add --related`` / ``vault link`` resolve a
    reference - via :func:`resolve_related_inputs` - then maps the
    canonical stem back to its backing file path.

    Args:
        ref: A document stem, filename (with or without ``.md``), absolute
            or relative path, or ``[[wiki-link]]``.
        root_dir: The project root whose ``.vault/`` holds the document.

    Returns:
        The absolute path to the backing document file.

    Raises:
        EditError: When the reference resolves to no vault document.
    """
    from vaultspec_core.vaultcore.resolve import (
        RelatedResolutionError,
        resolve_related_inputs,
    )
    from vaultspec_core.vaultcore.scanner import scan_vault

    try:
        resolved = resolve_related_inputs([ref], root_dir)
    except RelatedResolutionError as exc:
        raise EditError(
            f"Cannot resolve document: '{ref}'",
            {"path": ref},
        ) from exc

    if not resolved:
        raise EditError(f"Cannot resolve document: '{ref}'", {"path": ref})

    stem = resolved[0][2:-2]  # strip [[ ]]
    for doc_path in scan_vault(root_dir):
        if doc_path.stem == stem:
            return doc_path

    raise EditError(f"Resolved stem '{stem}' has no backing file", {"path": ref})


def _split_document(text: str) -> tuple[str, str]:
    """Split full document text into ``(frontmatter_block, body)``.

    The frontmatter block retains its leading and trailing ``---`` fences
    and the newline that follows the closing fence, so reassembling with
    ``frontmatter_block + body`` reproduces the original bytes exactly.
    A document with no frontmatter fence yields ``("", text)``.

    Args:
        text: Full document text with LF-normalised line endings.

    Returns:
        A two-tuple ``(frontmatter_block, body)``.
    """
    import re

    match = re.match(r"^(﻿?---[ \t]*\n.*?\n---[ \t]*\n?)(.*)$", text, re.DOTALL)
    if not match:
        return "", text
    return match.group(1), match.group(2)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_proposed(
    doc_path: Path, root_dir: Path, new_text: str
) -> list[dict[str, object]]:
    """Validate proposed full document text without writing it.

    Builds a single-document snapshot keyed on *doc_path* from the parsed
    *new_text* and runs the existing snapshot-consuming checkers
    (``frontmatter``, ``links``, ``body-links``) over only that document,
    so the conformance decision is made strictly pre-write.  No new
    validation logic is authored here.

    Args:
        doc_path: The path the proposed content will be written to.
        root_dir: Project root (used to relativise diagnostic paths).
        new_text: The full proposed document text (frontmatter + body).

    Returns:
        The combined diagnostics as plain dicts (``path``, ``message``,
        ``severity``, ``fixable``, ``fix_description``), ready to nest
        under ``error.checks``.
    """
    from vaultspec_core.vaultcore.checks import (
        check_body_links,
        check_frontmatter,
        check_links,
    )
    from vaultspec_core.vaultcore.parser import parse_vault_metadata

    metadata, body = parse_vault_metadata(new_text)
    snapshot = {doc_path: (metadata, body)}

    results = [
        check_frontmatter(root_dir, snapshot=snapshot, fix=False),
        check_links(root_dir, snapshot=snapshot, fix=False),
        check_body_links(root_dir, snapshot=snapshot),
    ]

    diagnostics: list[dict[str, object]] = []
    for result in results:
        for diag in result.diagnostics:
            diagnostics.append(_diag_to_dict(result.check_name, diag))
    return diagnostics


def _diag_to_dict(check_name: str, diag: CheckDiagnostic) -> dict[str, object]:
    """Render a :class:`CheckDiagnostic` as a JSON-safe dict.

    Args:
        check_name: The owning checker's name (e.g. ``"frontmatter"``).
        diag: The diagnostic to render.

    Returns:
        A dict carrying the check name, relative path, message, severity,
        and fix metadata.
    """
    payload = dataclasses.asdict(diag)
    payload["check"] = check_name
    payload["path"] = str(payload["path"]) if payload["path"] is not None else None
    payload["severity"] = str(payload["severity"])
    return payload


def _has_error(diagnostics: list[dict[str, object]]) -> bool:
    """Return ``True`` when any diagnostic is ERROR severity.

    Args:
        diagnostics: Rendered diagnostics from :func:`validate_proposed`.

    Returns:
        ``True`` if at least one diagnostic blocks the write.
    """
    return any(d["severity"] == "error" for d in diagnostics)


def _warnings_of(diagnostics: list[dict[str, object]]) -> list[str]:
    """Return the messages of WARNING-severity diagnostics.

    Args:
        diagnostics: Rendered diagnostics from :func:`validate_proposed`.

    Returns:
        The advisory messages that did not block the write.
    """
    return [
        str(d.get("message", "")) for d in diagnostics if d.get("severity") == "warning"
    ]


def _frontmatter_validate(proposed_lf: str) -> list[str]:
    """Return :meth:`DocumentMetadata.validate` errors for proposed text.

    Args:
        proposed_lf: The proposed full document text (LF-normalised).

    Returns:
        The validator's violation strings (empty when conformant).
    """
    from vaultspec_core.vaultcore.parser import parse_vault_metadata

    metadata: DocumentMetadata
    metadata, _body = parse_vault_metadata(proposed_lf)
    return metadata.validate()


# ---------------------------------------------------------------------------
# Optimistic concurrency
# ---------------------------------------------------------------------------


def enforce_blob_hash(doc_path: Path, expected: str | None) -> None:
    """Enforce optimistic-concurrency against the pre-write on-disk bytes.

    This function only compares hashes; it takes no lock itself.  A caller
    that follows a passing check with a write MUST hold
    :func:`~vaultspec_core.core.helpers.advisory_lock` on *doc_path*'s
    :func:`document_lock_target` across both the check and the write (as
    :func:`execute_edit` does), or a writer racing between the two can still
    land undetected.

    Args:
        doc_path: The document whose current bytes are hashed.
        expected: The blob OID the caller believes is current, or ``None``
            to skip the check.

    Raises:
        EditError: When *expected* is given and does not match the current
            on-disk blob OID, carrying ``conflict``, ``expected``, and
            ``actual`` in its payload.
    """
    from vaultspec_core.vaultcore.blob_hash import git_blob_oid

    if expected is None:
        return
    actual = git_blob_oid(doc_path.read_bytes())
    if actual != expected:
        raise EditError(
            "Blob-hash conflict: document changed on disk since it was read",
            {
                "conflict": True,
                "expected": expected,
                "actual": actual,
                "path": str(doc_path),
            },
        )


def document_lock_target(doc_path: Path, root_dir: Path) -> Path:
    """Return the per-document advisory-lock target for *doc_path*.

    :func:`~vaultspec_core.core.helpers.advisory_lock` derives its sentinel
    as a sibling of whatever path it is given (``<path>.lock``).  Passing
    *doc_path* itself would drop a permanent, untracked ``<document>.md.lock``
    beside the real document: `.vault/`'s managed-ignore policy
    (:mod:`vaultspec_core.core.gitignore`) enumerates lock sentinels by exact
    path for a small fixed set of files it owns (``.gitignore``,
    ``.mcp.json``, provider configs); it has no notion of - and deliberately
    does not glob for - arbitrary document-content locks, so a sibling
    sentinel is invisible to it and pollutes the tracked corpus.

    Instead the sentinel lives under the docs directory's already-ignored
    ``data/`` runtime subtree (the same convention
    :func:`~vaultspec_core.vaultcore.rename_engine.docs_lock_target` uses for
    the domain-wide rename sentinel), named by a SHA-1 digest of the
    document's path relative to the docs directory. A digest - rather than a
    flattened relative path - keeps the on-disk sentinel name fixed-length
    and legal on Windows regardless of how deep or long the real document
    path is, and is collision-free in practice: two distinct relative paths
    hashing to the same digest is not a real-world risk at this document
    count. Using the *resolved* relative path (not the raw string a caller
    supplied) means two references to the same on-disk file always derive
    the same sentinel even if they were spelled differently.

    Args:
        doc_path: The document being locked (resolved by
            :func:`resolve_document_path`, always an absolute, canonical
            path under the docs directory).
        root_dir: The project root whose ``.vault/`` holds the document.

    Returns:
        The lock target path; :func:`~vaultspec_core.core.helpers.advisory_lock`
        derives the actual ``<digest>.lock`` sentinel from it.
    """
    import hashlib

    from vaultspec_core.config import get_config

    docs_dir = (root_dir / get_config().docs_dir).resolve()
    resolved = doc_path.resolve()
    try:
        rel = resolved.relative_to(docs_dir)
    except ValueError:
        # Outside the docs directory (should not happen for a resolved
        # vault document) - fall back to the resolved absolute path so the
        # digest is still deterministic and collision-free per file.
        rel = resolved
    digest = hashlib.sha1(rel.as_posix().encode("utf-8"), usedforsecurity=False)
    return docs_dir / "data" / "locks" / digest.hexdigest()


@contextmanager
def document_write_lock(doc_path: Path, root_dir: Path) -> Generator[None]:
    """Hold *doc_path*'s per-document advisory lock for a read-modify-write.

    The boundary every non-``execute_edit`` document writer needs, and the
    reason it exists as a helper rather than three lines repeated per call
    site: a writer that reads a document, computes a replacement, and writes
    it back is only correct if the read and the write it authorizes are
    atomic with respect to every other vaultspec-core mutator on that file.
    Locking the write alone is worthless - the replacement was already
    derived from a revision another writer may have superseded, so the write
    lands as a deliberate, individually-atomic overwrite of content that was
    never read. That is the silent lost update: no truncation, no error on
    either side, and the losing writer reports success.

    Callers therefore wrap the WHOLE read-modify-write, not the write.

    The lock target is the same sentinel :func:`execute_edit` takes
    (:func:`document_lock_target`), so a fix pass and an editing session
    contend on one lock rather than two disjoint ones.

    :func:`~vaultspec_core.core.helpers.advisory_lock` deliberately no-ops
    when its sentinel's parent directory is absent, so the (per-machine,
    already-gitignored) lock directory is materialized first: a guard that
    silently skips is indistinguishable from one that held.

    Args:
        doc_path: The document about to be read and rewritten.
        root_dir: The project root whose ``.vault/`` holds the document.

    Yields:
        ``None``, with the per-document lock held for the block's duration.
    """
    from vaultspec_core.core.helpers import advisory_lock

    lock_target = document_lock_target(doc_path, root_dir)
    lock_target.parent.mkdir(parents=True, exist_ok=True)
    with advisory_lock(lock_target):
        yield


# ---------------------------------------------------------------------------
# Frontmatter field surgery (preserves unknown keys and CRLF)
# ---------------------------------------------------------------------------


def _serialise_block_list(key: str, values: list[str]) -> list[str]:
    """Render a YAML block list for *key* in the canonical vault style.

    Args:
        key: The frontmatter key (e.g. ``"tags"`` or ``"related"``).
        values: The list items; each rendered as ``  - 'value'``.

    Returns:
        The rendered lines, ``key: []`` when *values* is empty.
    """
    if not values:
        return [f"{key}: []"]
    lines = [f"{key}:"]
    lines.extend(f"  - '{v}'" for v in values)
    return lines


def _rewrite_frontmatter_field(
    frontmatter_block: str,
    key: str,
    new_lines: list[str],
) -> str:
    """Replace (or insert) a single frontmatter *key*'s lines.

    Operates only inside the leading ``---`` fence and touches only the
    block belonging to *key*; every other key, comment, and unknown field
    is preserved byte-for-byte.  When *key* is absent it is inserted
    immediately before the closing fence.

    Args:
        frontmatter_block: The frontmatter, including both ``---`` fences.
        key: The top-level key to rewrite (``date``, ``tags``, ``related``).
        new_lines: The replacement lines for the key's block.

    Returns:
        The rewritten frontmatter block.
    """
    lines = frontmatter_block.split("\n")
    out: list[str] = []
    in_block = False
    replaced = False
    close_idx: int | None = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        if in_block:
            # The key's block continues through indented list items only.
            if line[:1] in (" ", "\t"):
                continue
            in_block = False

        # Closing fence: remember its position for an insert-if-absent.
        if stripped == "---" and i > 0 and close_idx is None and out:
            close_idx = len(out)

        if (
            not in_block
            and (stripped == f"{key}:" or stripped.startswith(f"{key}:"))
            and not stripped.startswith("-")
        ):
            # Found the key line (block, inline, or empty form). Replace its
            # whole block with the new rendering.
            out.extend(new_lines)
            replaced = True
            in_block = True
            close_idx = None
            continue

        out.append(line)

    if not replaced:
        # Insert before the closing fence (the last `---`).
        insert_at = len(out) - 1
        for j in range(len(out) - 1, -1, -1):
            if out[j].strip() == "---":
                insert_at = j
                break
        out[insert_at:insert_at] = new_lines

    return "\n".join(out)


def _apply_frontmatter_edits(
    frontmatter_block: str,
    *,
    date: str | None,
    tags: list[str] | None,
    related: list[str] | None,
) -> str:
    """Apply the provided field edits to a frontmatter block.

    Only the fields explicitly supplied (non-``None``) are rewritten; every
    other key is preserved.  Returns the edited block (still fenced).

    Args:
        frontmatter_block: The frontmatter, including both ``---`` fences.
        date: New ``date`` value, or ``None`` to leave unchanged.
        tags: New ``tags`` list, or ``None`` to leave unchanged.
        related: New ``related`` list of ``[[wiki-link]]`` strings, or
            ``None`` to leave unchanged.

    Returns:
        The frontmatter block with the requested fields replaced.
    """
    block = frontmatter_block
    if date is not None:
        block = _rewrite_frontmatter_field(block, "date", [f"date: '{date}'"])
    if tags is not None:
        block = _rewrite_frontmatter_field(
            block, "tags", _serialise_block_list("tags", tags)
        )
    if related is not None:
        block = _rewrite_frontmatter_field(
            block, "related", _serialise_block_list("related", related)
        )
    return block


# ---------------------------------------------------------------------------
# Compose / write
# ---------------------------------------------------------------------------


def _compose_new_text(
    doc_path: Path,
    *,
    new_body: str | None,
    date: str | None,
    tags: list[str] | None,
    related: list[str] | None,
) -> tuple[str, str]:
    """Compose the proposed full document text from the on-disk original.

    Reads the document CRLF-preservingly, applies the body and/or
    frontmatter edits, and refreshes the ``modified:`` stamp.  Returns the
    LF-normalised proposed text (for validation) and the source newline
    convention (for the eventual write).

    Args:
        doc_path: The document to edit.
        new_body: Replacement body text (LF-normalised), or ``None`` to keep.
        date: New ``date`` value, or ``None`` to keep.
        tags: New ``tags`` list, or ``None`` to keep.
        related: New ``related`` list, or ``None`` to keep.

    Returns:
        A two-tuple ``(proposed_text_lf, source_newline)``.

    Raises:
        EditError: When the document cannot be read.
    """
    from vaultspec_core.vaultcore.models import refresh_modified_stamp, vault_today
    from vaultspec_core.vaultcore.related_surgery import read_preserve_newlines

    try:
        content, source_newline = read_preserve_newlines(doc_path)
    except (OSError, UnicodeDecodeError) as exc:
        raise EditError(f"Cannot read document '{doc_path}': {exc}", {}) from exc

    frontmatter_block, body = _split_document(content)

    if date is not None or tags is not None or related is not None:
        frontmatter_block = _apply_frontmatter_edits(
            frontmatter_block, date=date, tags=tags, related=related
        )

    if new_body is not None:
        body = new_body

    proposed = frontmatter_block + body
    proposed = refresh_modified_stamp(proposed, vault_today())
    return proposed, source_newline


def _write_proposed(doc_path: Path, proposed_lf: str, source_newline: str) -> None:
    """Atomically write proposed text, restoring the original on failure.

    Args:
        doc_path: The destination document.
        proposed_lf: The proposed text (LF-normalised).
        source_newline: The newline convention to restore on write.

    Raises:
        EditError: When the destination cannot be written - most often
            because it vanished between resolution and write.
            :func:`~vaultspec_core.vaultcore.related_surgery.atomic_write_restore`
            copies the original to a ``.bak`` before its own ``try``, so a
            missing file raises there rather than through its restore path.
            The advisory lock serializes vaultspec-core's own mutators
            against each other, but nothing binds an external actor: an open
            editor, a ``git checkout``, or a sync client can remove the file
            inside this window. Folding the ``OSError`` into the pipeline's
            own error type keeps that a reported failure the caller can act
            on, rather than a traceback escaping :func:`execute_edit` - whose
            contract is that every reachable failure arrives as an
            :class:`EditResult` with ``status == "failed"``.
    """
    from vaultspec_core.vaultcore.related_surgery import atomic_write_restore

    out = (
        proposed_lf
        if source_newline == "\n"
        else proposed_lf.replace("\n", source_newline)
    )
    try:
        atomic_write_restore(doc_path, out)
    except OSError as exc:
        raise EditError(
            f"Could not write {doc_path.name}: {exc}",
            {"path": str(doc_path), "write_failed": True},
        ) from exc


def invalidate_graph_cache(root_dir: Path) -> None:
    """Drop the graph cache after a mutating write.

    Byte-for-byte equivalent to
    :func:`vaultspec_core.cli._cache_hook.invalidate_graph_cache`, inlined
    here so the engine depends only on the ``graph`` layer and never on the
    ``cli`` layer.  Never raises: a missing cache or a delete error degrades
    to a no-op because the fingerprint manifest remains a correct fallback
    guard and a failed invalidation must not break the write it followed.

    Args:
        root_dir: Project root whose graph cache is dropped.
    """
    import logging

    from vaultspec_core.graph import cache as cache_mod

    try:
        cache_mod.cache_path(root_dir).unlink(missing_ok=True)
    except OSError as exc:
        logging.getLogger(__name__).debug(
            "Graph cache invalidation skipped for %s: %s", root_dir, exc
        )


# ---------------------------------------------------------------------------
# Public core
# ---------------------------------------------------------------------------


def execute_edit(
    root_dir: Path,
    *,
    ref: str,
    new_body: str | None = None,
    date: str | None = None,
    tags: list[str] | None = None,
    related: list[str] | None = None,
    expected_blob_hash: str | None = None,
    run_checks: bool = True,
    dry_run: bool = False,
) -> EditResult:
    """Run the resolve -> guard -> compose -> validate -> write pipeline.

    The single shared implementation behind ``vault set-body`` /
    ``vault set-frontmatter`` / ``vault edit`` and the MCP ``edit`` tool.
    Always returns an :class:`EditResult`: every reachable failure
    (unresolvable reference, blob-hash conflict, validation refusal, or
    read/write error) is folded into ``status == "failed"`` with a
    structured ``error`` payload, so batch callers report it as a per-item
    result rather than a whole-call error. This includes the target
    vanishing (deleted or replaced by something other than vaultspec-core -
    the advisory lock is not enforced on external tools) between the guard
    passing and the write landing: :func:`_write_proposed` folds that
    ``OSError`` into the pipeline's own :class:`EditError` itself, and the
    symmetric post-write re-read here does the same, so nothing escapes
    uncaught regardless of which of the two file operations hits the
    vanished target.

    The guard-through-write sequence (:func:`enforce_blob_hash`, compose,
    validate, and the eventual write) runs under a per-document
    :func:`~vaultspec_core.core.helpers.advisory_lock` on the sentinel
    :func:`document_lock_target` derives (a digest keyed under the docs
    directory's ignored ``data/`` subtree, not a visible sibling of the
    document), so the hash check and the write it authorizes are atomic with
    respect to any other vaultspec-core mutator racing on the same file: no
    writer can land between the check and the write, which would otherwise
    let a concurrent change through undetected (a silent lost update).

    Args:
        root_dir: The project root whose ``.vault/`` holds the document.
        ref: The document reference (stem, filename, path, or wiki-link).
        new_body: Replacement body text (LF-normalised), or ``None`` for no
            body edit.
        date: New ``date`` value, or ``None``.
        tags: New ``tags`` list (already ``#``-prefixed), or ``None``.
        related: New ``related`` list (already resolved to ``[[wiki-link]]``
            strings), or ``None``.
        expected_blob_hash: Pre-write concurrency guard, or ``None`` to skip.
        run_checks: Whether to run the snapshot conformance checkers before
            writing (the frontmatter model validator always runs).
        dry_run: When ``True``, do everything except the write.

    Returns:
        The typed :class:`EditResult` for the operation.
    """
    from vaultspec_core.core.helpers import advisory_lock
    from vaultspec_core.vaultcore.blob_hash import git_blob_oid

    try:
        doc_path = resolve_document_path(ref, root_dir)
        lock_target = document_lock_target(doc_path, root_dir)

        # advisory_lock no-ops when its sentinel's parent directory is
        # missing (deliberately, to avoid directory-creation side effects on
        # a preview). A dry run honors that and may end up unlocked if the
        # runtime dir has never been created; a real write must never
        # silently skip the guard, so it materializes the (per-machine,
        # already-gitignored) lock directory itself before locking.
        if not dry_run:
            lock_target.parent.mkdir(parents=True, exist_ok=True)

        # The guard, the composition it authorizes, and the eventual write all
        # run under one per-document lock: a hash check that passed outside a
        # lock could still be invalidated by a writer that lands before the
        # write actually happens. Locking only the write would not help either
        # since the check itself must be re-taken inside the same critical
        # section. See module docstring / execute_edit docstring.
        with advisory_lock(lock_target):
            # Concurrency guard is enforced against the *current* on-disk
            # bytes, before any mutation or even composition is trusted.
            enforce_blob_hash(doc_path, expected_blob_hash)

            proposed_lf, source_newline = _compose_new_text(
                doc_path,
                new_body=new_body,
                date=date,
                tags=tags,
                related=related,
            )

            # Frontmatter conformance is the model's own validator, run
            # pre-write.
            frontmatter_errors = _frontmatter_validate(proposed_lf)

            checks: list[dict[str, object]] = []
            if run_checks:
                checks = validate_proposed(doc_path, root_dir, proposed_lf)

            if frontmatter_errors or _has_error(checks):
                error: dict[str, object] = {
                    "path": str(doc_path),
                    "refused": True,
                    "checks": checks,
                }
                if frontmatter_errors:
                    error["errors"] = frontmatter_errors
                return EditResult(
                    status="failed",
                    path=str(doc_path),
                    checks=checks,
                    error=error,
                    warnings=_warnings_of(checks),
                )

            original_bytes = doc_path.read_bytes()
            proposed_bytes = (
                proposed_lf
                if source_newline == "\n"
                else proposed_lf.replace("\n", source_newline)
            ).encode("utf-8", errors="surrogateescape")

            changed = proposed_bytes != original_bytes

            if dry_run:
                return EditResult(
                    status="updated" if changed else "unchanged",
                    path=str(doc_path),
                    blob_hash=git_blob_oid(proposed_bytes),
                    checks=checks,
                    warnings=_warnings_of(checks),
                    dry_run=True,
                    changed=changed,
                )

            if changed:
                # _write_proposed raises the typed EditError itself (see its
                # docstring) when the target vanished out from under an
                # external actor the advisory lock cannot bind - no OSError
                # can escape this call.
                _write_proposed(doc_path, proposed_lf, source_newline)
                invalidate_graph_cache(root_dir)

            try:
                # Symmetric with the write above: the same external actor
                # could remove the just-written file before this re-read,
                # and nothing lower in the stack converts that for us here.
                post_hash = git_blob_oid(doc_path.read_bytes())
            except OSError as exc:
                raise EditError(
                    f"Cannot read document '{doc_path}' after write: {exc}",
                    {"path": str(doc_path)},
                ) from exc
            return EditResult(
                status="updated" if changed else "unchanged",
                path=str(doc_path),
                blob_hash=post_hash,
                checks=checks,
                warnings=_warnings_of(checks),
            )
    except EditError as exc:
        return EditResult(
            status="failed",
            path=str(exc.data.get("path")) if exc.data.get("path") else None,
            error={"message": exc.message, **exc.data},
        )
