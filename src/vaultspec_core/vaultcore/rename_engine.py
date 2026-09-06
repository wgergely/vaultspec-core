"""Shared transactional rename engine for vaultspec CRUD surfaces.

This module holds the reusable transaction mechanics that every rename/move
surface in the CLI converges onto: a root-generalized containment guard, a
symlink-safe byte restore, and a :class:`RenameTransaction` context manager
that journals each mutation and rolls the managed root back byte-for-byte on
any failure while holding a per-domain advisory lock for its lifetime.

The mechanics are extracted verbatim from the hardened ``rename_feature``
backend (formerly the bespoke ``_RenameJournal`` / ``_snapshot_docs`` /
``_rollback_rename`` helpers in :mod:`vaultspec_core.vaultcore.query`) so the
behavior every caller inherits is identical to the one the feature-rename
adversarial suites already pin. The single generalization is that containment
and the snapshot set are parameterized by the caller's managed root rather than
hardcoded to the docs directory, so the same engine protects renames under
``.vault/`` and under ``.vaultspec/``.
"""

from __future__ import annotations

import contextlib
import logging
import shutil
from typing import TYPE_CHECKING

from ..core.exceptions import VaultSpecError
from ..core.helpers import advisory_lock, atomic_write_bytes
from .rename_ops import rename_document_path

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path
    from typing import Literal

logger = logging.getLogger(__name__)

#: Re-exported for every CRUD surface that reaches into this module's
#: containment guard: :mod:`vaultspec_core.core.hooks`,
#: :mod:`vaultspec_core.core.resources`, :mod:`vaultspec_core.vaultcore.batch_archive`,
#: :mod:`vaultspec_core.vaultcore.exec_recovery`, and
#: :mod:`vaultspec_core.vaultcore.query_rename`.
__all__ = ["RollbackError", "assert_within"]


class RollbackError(VaultSpecError):
    """A transaction rollback could not restore every snapshotted document.

    Raised out of :meth:`RenameTransaction.__exit__` when one or more
    snapshot restores failed, chained (``raise ... from``) to the original
    exception that triggered the rollback so the operator sees both the
    operation that failed and the fact that recovery did not complete.
    """


def assert_within(managed_root: Path, path: Path) -> Path:
    """Return *path* iff its real location is inside *managed_root*, else raise.

    Resolves every symlink and ``..`` segment in *path* (and in any existing
    ancestor of a not-yet-created destination) and refuses the operation when
    the result escapes the managed tree.  This is the containment backstop that
    prevents a rename from reading, writing, moving, or deleting a file whose
    true location is outside the managed root - including the case where a
    subdirectory or a document is itself a symlink pointing outside the
    project.

    Args:
        managed_root: The root the rename is allowed to operate within
            (e.g. the vault document root, or a ``.vaultspec`` resource root).
        path: A candidate source or destination path inside the rename plan.

    Returns:
        *path* unchanged when it is contained.

    Raises:
        VaultSpecError: When *path* resolves outside *managed_root*.
    """
    real_docs = managed_root.resolve(strict=False)
    real_path = path.resolve(strict=False)
    if real_path != real_docs and real_docs not in real_path.parents:
        raise VaultSpecError(
            "Refusing to operate on a path outside the managed directory tree "
            f"(possible symlink or traversal escape): {path}"
        )
    return path


def _safe_restore_bytes(path: Path, original: bytes) -> None:
    """Restore *original* bytes to *path* without writing through a symlink.

    A symlinked rollback target is unlinked first so the bytes land on a
    fresh regular file at the in-vault path rather than following the link
    to an out-of-bounds destination. That unlink is what makes the restore
    succeed rather than refuse; :func:`~vaultspec_core.core.helpers.atomic_write_bytes`
    would reject the link outright, and it stays underneath as the backstop
    for a link created between the two calls.

    The write itself goes through ``atomic_write_bytes`` rather than
    ``Path.write_bytes``. ``write_bytes`` truncates the destination to zero
    before it writes, so an interruption between the truncate and the flush
    left a zero-length document on the one code path whose entire purpose is
    to prevent data loss (issue #456). The temp-write-fsync-rename sequence
    leaves the destination either untouched or complete, and inherits the
    ``_replace_atomic`` retry budget that rides out a transiently held handle
    on Windows.
    """
    if path.is_symlink():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(path, original)


def docs_lock_target(docs_dir: Path) -> Path:
    """Return the advisory-lock target serializing ``.vault`` docs-domain renames.

    The value is the argument to :func:`~vaultspec_core.core.helpers.advisory_lock`,
    which appends ``.lock`` to derive the OS sentinel - here
    ``<docs_dir>/data/.vault.lock`` (the ``data/`` subtree is already gitignored, so
    no lock file is committed). Every docs-domain mutator (feature rename, document
    rename, the structure-rename cascade) MUST pass this exact value so they
    serialize on one sentinel; ``advisory_lock`` no-ops when ``data/`` is absent.
    """
    return docs_dir / "data" / ".vault"


def resource_lock_target(vaultspec_dir: Path) -> Path:
    """Return the advisory-lock target serializing ``.vaultspec`` resource renames.

    The OS sentinel is ``<vaultspec_dir>/.resources.lock`` (``.vaultspec/*.lock`` is
    already gitignored). Every resource-domain mutator (resource rename, hook rename)
    MUST pass this exact value to serialize on one sentinel.
    """
    return vaultspec_dir / ".resources"


def iter_snapshot_docs(managed_root: Path) -> Iterator[Path]:
    """Yield every non-archive ``*.md`` under *managed_root* for snapshotting.

    This is the canonical transaction-snapshot basis shared by every docs-domain
    rename: every ``*.md`` under the managed root except those inside an
    ``_archive`` subtree or any dot-prefixed directory (``.obsidian``,
    ``.trash``, ...). The set is handed to
    :meth:`RenameTransaction.snapshot`, which applies the per-file
    symlink/non-file skip and read-failure handling.

    Both the feature rename (whole-tree mutation) and the single-document rename
    (file move plus ``related:`` cascade) snapshot this exact set so the rollback
    journal is a guaranteed superset of what the apply can mutate: the
    ``related:`` cascade
    (:func:`~vaultspec_core.vaultcore.rename_ops.rewrite_incoming_refs`) also
    excludes ``_archive`` and dot-prefixed directories, so a document the cascade
    can rewrite is always one this iterator captures - and an archived or hidden
    document is never rewritten *nor* snapshotted. Deriving the snapshot from a
    stale graph cache instead would risk missing a rewritten doc and leaving the
    rollback journal incomplete.

    Args:
        managed_root: The vault document root (``<root>/<docs_dir>``).

    Yields:
        Each candidate document path, in ``rglob`` order.
    """
    if not managed_root.is_dir():
        return
    for md in managed_root.rglob("*.md"):
        try:
            rel_parts = md.relative_to(managed_root).parts
        except ValueError:
            continue
        if any(p == "_archive" or p.startswith(".") for p in rel_parts):
            continue
        yield md


class RenameTransaction:
    """A reverse-journaled, lock-protected rename transaction.

    Used as a context manager, it acquires a per-domain advisory lock for its
    lifetime (when a ``lock_target`` is supplied) and journals every mutation
    the caller funnels through it.  If an exception propagates out of the
    ``with`` block the journal is walked in reverse to restore the managed root
    byte-for-byte to its pre-transaction state, then the exception is allowed to
    propagate unchanged; on clean exit the lock is released and nothing is
    rolled back.

    The journal field semantics mirror the former ``_RenameJournal`` exactly so
    the rollback ordering is identical to the hardened feature-rename backend:

    Attributes:
        managed_root: The root every :meth:`rename` endpoint is contained to.
        lock_target: The advisory-lock target acquired for the transaction's
            lifetime, or ``None`` to run without a lock.  ``advisory_lock``
            skips locking when the target's parent directory is absent, and the
            transaction never creates that parent.
        document_lock_targets: Per-document advisory-lock targets for the
            documents this transaction will MUTATE, acquired inside the domain
            lock. Callers derive them from
            :func:`~vaultspec_core.vaultcore.edit_engine.document_lock_target`
            and are responsible for creating the parent directory, since
            ``advisory_lock`` silently skips a target whose parent is absent.
            Pass nothing to run on the domain lock alone - the behaviour every
            caller had before per-document locking existed. Supply only a set
            the caller can determine confidently: widening it to the whole
            snapshot tree would be a global edit freeze in N acquisitions,
            which costs more than the domain lock it sits beside and buys
            nothing.
        file_renames: ``(src, dst)`` renames actually applied, in order.
        created_dirs: Directories created during apply.
        removed_dirs: Directories removed once emptied during apply.
        created_files: Files created during apply.
        snapshots: Original bytes of every snapshotted file, keyed by path.
    """

    def __init__(
        self,
        managed_root: Path,
        *,
        lock_target: Path | None = None,
        document_lock_targets: Iterable[Path] | None = None,
    ) -> None:
        self.managed_root = managed_root
        self.lock_target = lock_target
        self.document_lock_targets = sorted(set(document_lock_targets or ()), key=str)
        self._stack = contextlib.ExitStack()
        self.file_renames: list[tuple[Path, Path]] = []
        self.created_dirs: list[Path] = []
        self.removed_dirs: list[Path] = []
        self.created_files: list[Path] = []
        self.snapshots: dict[Path, bytes] = {}

    def __enter__(self) -> RenameTransaction:
        """Acquire the domain lock, then any per-document locks, and return self.

        The acquisition ORDER is the deadlock argument, so it lives here rather
        than at each call site: the domain sentinel is taken first, then the
        per-document sentinels in a deterministic sorted order.
        :func:`~vaultspec_core.vaultcore.edit_engine.execute_edit` takes only a
        per-document sentinel and never requests the domain lock, so no caller
        can hold one while waiting on the other and no cycle is constructible.
        Centralising it means a call site cannot re-implement the convention
        slightly wrong.

        Holding the per-document locks HERE rather than around the ``with``
        block also keeps them held through rollback: :meth:`__exit__` restores
        the journal before closing this stack, so a concurrent edit cannot race
        the restore of a document the transaction mutated.
        """
        if self.lock_target is not None:
            self._stack.enter_context(advisory_lock(self.lock_target))
        for target in self.document_lock_targets:
            self._stack.enter_context(advisory_lock(target))
        return self

    def __exit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> Literal[False]:
        """Roll back on a propagating exception, then release the locks.

        Rollback runs while EVERY lock is still held - the domain sentinel and
        the per-document sentinels alike - so the restore is serialized both
        against other domain mutators and against a concurrent
        :func:`~vaultspec_core.vaultcore.edit_engine.execute_edit` on a
        document this transaction mutated. The ordering is load-bearing and is
        why the per-document locks are acquired here rather than by the caller:
        held on the caller's side they would already have been released by the
        time this runs, leaving the restore racing an edit. The exception is
        never suppressed.

        A rollback that cannot restore every snapshot raises
        :class:`RollbackError`, which replaces the in-flight exception as the
        one the caller sees. It does not replace the *information*: the
        triggering exception is named in the message and attached as
        ``__cause__``, so a plain-text CLI renderer that prints only
        ``str(exc)`` and a traceback both carry the whole story. Swallowing
        the rollback failure to preserve the original would report a clean
        rollback over a mixed vault, which is the worse of the two losses
        (issue #456).

        Raises:
            RollbackError: When the rollback ran but could not restore every
                snapshotted document. Its ``__cause__`` is the original
                exception that triggered the rollback.
        """
        trigger = exc_val if isinstance(exc_val, BaseException) else None
        try:
            if exc_type is not None:
                try:
                    self._rollback(trigger)
                except RollbackError as rollback_exc:
                    raise rollback_exc from trigger
        finally:
            self._stack.close()
        return False

    def snapshot(self, paths: Iterable[Path]) -> None:
        """Record the original bytes of a caller-supplied file set.

        The caller decides the participating set; the engine never rglobs a
        root.  Per-file behavior matches the former ``_snapshot_docs``:
        symlinks and non-files are skipped (a symlinked file is not a
        legitimate managed document and snapshotting it would pull an
        out-of-bounds target's bytes into the rollback journal), and an
        unreadable file logs a warning rather than aborting.

        Args:
            paths: The files whose pre-transaction bytes to capture.
        """
        for path in paths:
            if path.is_symlink() or not path.is_file():
                continue
            try:
                self.snapshots[path] = path.read_bytes()
            except OSError as exc:
                logger.warning("Could not snapshot %s for rollback: %s", path, exc)

    def rename(self, src: Path, dst: Path) -> bool:
        """Containment-check both endpoints, rename, and journal on success.

        Args:
            src: Source path (contained to :attr:`managed_root`).
            dst: Destination path (contained to :attr:`managed_root`).

        Returns:
            The result of
            :func:`~vaultspec_core.vaultcore.rename_ops.rename_document_path`; a
            journal entry is recorded only when the rename succeeds.

        Raises:
            VaultSpecError: When either endpoint resolves outside the root.
        """
        assert_within(self.managed_root, src)
        assert_within(self.managed_root, dst)
        ok = rename_document_path(src, dst)
        if ok:
            self.file_renames.append((src, dst))
        return ok

    def record_created_file(self, path: Path) -> None:
        """Journal a file created during apply (deleted first on rollback)."""
        self.created_files.append(path)

    def record_created_dir(self, path: Path) -> None:
        """Journal a directory created during apply (dropped on rollback)."""
        self.created_dirs.append(path)

    def record_removed_dir(self, path: Path) -> None:
        """Journal a directory removed during apply (recreated on rollback)."""
        self.removed_dirs.append(path)

    def _rollback(self, trigger: BaseException | None = None) -> None:
        """Walk the journal in reverse to restore the pre-transaction state.

        The order is deliberate and identical to the former
        ``_rollback_rename``: delete created files first, recreate removed
        directories so renamed records have a home to return to, reverse the
        file renames (LIFO), drop any directories created during apply, and
        finally restore every snapshot's original bytes (which also recreates
        any deleted file captured in the snapshot set).

        The snapshot stage is the only one that reports failure. Every earlier
        stage is best-effort cleanup of state the restore stage supersedes; a
        snapshot that will not restore is a document left holding the failed
        operation's bytes, which is a mixed vault, not a debug-log event
        (issue #456). Failures are aggregated rather than raised on the first
        one so a single unrestorable path cannot strand the documents behind
        it in the iteration order.

        Args:
            trigger: The exception that caused the rollback, named in the
                failure message so the operator is not shown a recovery
                failure detached from the operation that provoked it.

        Raises:
            RollbackError: When one or more snapshotted documents could not be
                restored. :meth:`__exit__` chains it to *trigger*.
        """
        unrestored: list[tuple[Path, OSError]] = []

        for path in self.created_files:
            with contextlib.suppress(OSError):
                if path.is_file():
                    path.unlink()

        for directory in self.removed_dirs:
            with contextlib.suppress(OSError):
                directory.mkdir(parents=True, exist_ok=True)

        for src, dst in reversed(self.file_renames):
            if not dst.exists():
                continue
            if rename_document_path(dst, src):
                continue
            with contextlib.suppress(OSError):
                shutil.move(str(dst), str(src))

        for directory in reversed(self.created_dirs):
            with contextlib.suppress(OSError):
                if directory.is_dir() and not any(directory.iterdir()):
                    directory.rmdir()

        for path, original in self.snapshots.items():
            try:
                # If the key became a symlink since the snapshot, restore through
                # a fresh regular file (never write through the link to an
                # out-of-bounds target). Otherwise restore only when content
                # drifted. ``is_symlink()`` is checked first so the short-circuit
                # avoids a symlink-following ``read_bytes()``.
                if (
                    path.is_symlink()
                    or not path.exists()
                    or path.read_bytes() != original
                ):
                    _safe_restore_bytes(path, original)
            except OSError as exc:
                # Keep restoring the rest of the journal - one unrestorable
                # document must not strand the others - but record it, and
                # let the aggregate below refuse to exit quietly.
                logger.error("Rollback could not restore %s: %s", path, exc)
                unrestored.append((path, exc))

        if unrestored:
            listing = "; ".join(f"{path}: {exc}" for path, exc in unrestored)
            provoked = (
                f" The operation was rolled back because "
                f"{type(trigger).__name__}: {trigger}."
                if trigger is not None
                else ""
            )
            raise RollbackError(
                f"Rollback could not restore {len(unrestored)} "
                f"{'document' if len(unrestored) == 1 else 'documents'}; "
                f"the vault is in a mixed state: {listing}.{provoked}",
                hint=(
                    "Inspect the listed paths and restore them from version "
                    "control before running another vault mutation."
                ),
            )
