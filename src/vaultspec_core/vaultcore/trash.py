"""Pre-deletion snapshots of ``.vault/`` documents.

Every code path that removes a document a human authored copies it here
first. The copy lands under ``.vault/.trash/<timestamp>-<label>/`` at its
vault-relative path, so an operator can find the file by the name it had and
copy it back by hand.

Why this exists. Until this module, recovery from a destructive migration was
git and only git: ``.vault/*.md`` is tracked, so the *committed* form of a
removed document survives in the prior commit. Anything authored since the
last commit did not, and a workspace whose ``.vault/`` is not in git at all
had no recovery whatsoever. The snapshot is the recovery that does not
require the user to have already done something.

Refusal, not best effort. :meth:`TrashWriter.capture` raises
:class:`SnapshotError` when a copy cannot be written or verified, and its
callers propagate that as a migration failure *before* unlinking anything.
Deleting because the backup failed is strictly worse than not deleting, so a
full disk or a read-only ``.vault/`` stops the migration rather than
proceeding without a net.

Retention: none, deliberately. Nothing in vaultspec ever deletes a snapshot.
A safety net that expires on a timer is not a safety net - the loss a user
notices late is exactly the one an age-based sweep would already have
collected - and the directory is the only copy of an uncommitted document.
The cost is bounded and visible: the writer reports its file count and byte
total to the caller so the command that created it says how much it wrote,
and ``.vault/.trash/`` is in the managed gitignore block, so the growth stays
out of the repository. Reclaiming the space is a directory deletion the
operator performs when they have decided the documents are not coming back.

No restore command. A snapshot is a plain directory of unmodified files at
their original relative paths, with a ``RESTORE.txt`` index naming each one's
origin. A verb that copied them back would have to answer what happens when
the destination now exists, which is a question only the operator can answer
per file, and it would present the copy as *managed* state when the honest
description is that it is a pile of files. Restoring is ``cp``.

Locking: none, deliberately. Each writer owns a directory named for the
instant and process that created it, so no two writers ever address the same
path and there is nothing to serialise. This matters beyond economy: the
migration driver already holds the manifest lock while migration bodies run
and :func:`~vaultspec_core.vaultcore.exec_fold.apply_fold` takes the docs
lock beneath it, and :func:`~vaultspec_core.core.helpers.advisory_lock` is
not reentrant, so a third lock acquired under those two would add an edge to
a cycle rather than protect anything.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

__all__ = [
    "RESTORE_FILENAME",
    "TRASH_DIR_NAME",
    "SnapshotError",
    "TrashSnapshot",
    "TrashWriter",
    "snapshot_paths",
    "trash_root",
]

logger = logging.getLogger(__name__)

#: Directory under the docs root that holds every snapshot.
TRASH_DIR_NAME = ".trash"

#: Per-snapshot index naming each copy's origin, written beside the copies.
RESTORE_FILENAME = "RESTORE.txt"

_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"


class SnapshotError(RuntimeError):
    """Raised when a pre-deletion snapshot cannot be written or verified.

    Callers must treat this as fatal to the operation that was about to
    delete: the whole point of the snapshot is that the deletion does not
    happen without it.
    """


@dataclass(frozen=True)
class TrashSnapshot:
    """A completed snapshot directory.

    Attributes:
        root: The snapshot directory, e.g.
            ``.vault/.trash/20260906-120000-exec_ledger_only/``.
        files: Number of documents copied into it.
        total_bytes: Combined size of those documents.
    """

    root: Path
    files: int
    total_bytes: int


def trash_root(workspace: Path) -> Path:
    """Return the workspace's snapshot root, ``.vault/.trash/``.

    Args:
        workspace: Workspace root directory.

    Returns:
        The directory holding every snapshot. Not created by this call.
    """
    from ..config import get_config

    return workspace / get_config().docs_dir / TRASH_DIR_NAME


def human_bytes(count: int) -> str:
    """Render *count* bytes in the largest unit that keeps it readable."""
    size = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"  # pragma: no cover - unreachable, loop returns at GB


class TrashWriter:
    """Copies documents into one snapshot directory before they are deleted.

    A writer is created per operation, not per file: every document a single
    migration or fold removes lands in the same timestamped directory, so the
    operator has one place to look rather than one per folder. The directory
    itself is created lazily on the first capture, so an operation that
    removes nothing leaves no trace.
    """

    def __init__(self, workspace: Path, label: str) -> None:
        """Prepare a writer for *workspace*, named for *label*.

        Args:
            workspace: Workspace root directory.
            label: Short slug naming the operation, e.g. a migration name.
                Appears in the directory name and in ``RESTORE.txt``.
        """
        from ..config import get_config

        self._workspace = workspace
        self._docs_dir = workspace / get_config().docs_dir
        self._label = label
        self._root: Path | None = None
        self._created = _dt.datetime.now().replace(microsecond=0)
        self._entries: list[tuple[str, str]] = []
        self._total_bytes = 0

    @property
    def root(self) -> Path | None:
        """The snapshot directory, or ``None`` while nothing has been copied."""
        return self._root

    @property
    def files(self) -> int:
        """How many documents have been copied so far."""
        return len(self._entries)

    @property
    def total_bytes(self) -> int:
        """Combined size of the documents copied so far."""
        return self._total_bytes

    def capture(self, paths: Iterable[Path]) -> None:
        """Copy every existing path in *paths* into this snapshot.

        Non-existent paths and directories are ignored, so a caller may pass
        a plan's whole removal set without pre-filtering. The copies are
        verified by size against their sources before this returns, so a
        short write from a full disk surfaces here rather than after the
        originals are gone.

        Args:
            paths: Documents that are about to be deleted.

        Raises:
            SnapshotError: When the snapshot directory cannot be created, a
                copy fails or reads back at the wrong size, or a path lies
                outside the workspace and therefore has no relative home
                inside the snapshot. The caller must abort without deleting.
        """
        pending = [path for path in paths if path.is_file()]
        if not pending:
            return

        root = self._ensure_root()
        for source in pending:
            relative = self._relative_of(source)
            destination = root / relative
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                copied = destination.stat().st_size
                original = source.stat().st_size
            except OSError as exc:
                self._abandon()
                raise SnapshotError(
                    f"could not snapshot {source} to {destination}: {exc}"
                ) from exc
            if copied != original:
                self._abandon()
                raise SnapshotError(
                    f"snapshot of {source} is {copied} bytes, expected {original}"
                )
            self._entries.append((relative.replace(os.sep, "/"), self._origin(source)))
            self._total_bytes += original

        self._write_index()
        logger.info(
            "Snapshotted %d document(s) (%s) to %s",
            self.files,
            human_bytes(self._total_bytes),
            root,
        )

    def result(self) -> TrashSnapshot | None:
        """Return the completed snapshot, or ``None`` if nothing was copied."""
        if self._root is None:
            return None
        return TrashSnapshot(
            root=self._root, files=self.files, total_bytes=self._total_bytes
        )

    def _ensure_root(self) -> Path:
        """Create and remember this writer's snapshot directory."""
        if self._root is not None:
            return self._root
        base = self._docs_dir / TRASH_DIR_NAME
        stamp = self._created.strftime(_TIMESTAMP_FORMAT)
        candidate = base / f"{stamp}-{self._label}"
        suffix = 1
        try:
            while candidate.exists():
                # A second operation within the same second, or a re-run
                # against a workspace that already carries today's snapshot.
                candidate = base / f"{stamp}-{self._label}-{suffix}"
                suffix += 1
            candidate.mkdir(parents=True)
        except OSError as exc:
            raise SnapshotError(
                f"could not create snapshot directory under {base}: {exc}"
            ) from exc
        self._root = candidate
        return candidate

    def _relative_of(self, source: Path) -> str:
        """Return *source*'s path inside the snapshot, mirroring the vault."""
        for anchor in (self._docs_dir, self._workspace):
            try:
                return str(source.relative_to(anchor))
            except ValueError:
                continue
        raise SnapshotError(
            f"refusing to delete {source}: it lies outside {self._workspace} "
            "and cannot be snapshotted"
        )

    def _origin(self, source: Path) -> str:
        """Return *source* as a workspace-relative path for ``RESTORE.txt``."""
        try:
            return str(source.relative_to(self._workspace)).replace(os.sep, "/")
        except ValueError:  # pragma: no cover - _relative_of rejects these first
            return str(source)

    def _write_index(self) -> None:
        """Write (or rewrite) ``RESTORE.txt`` describing every copy so far."""
        root = self._root
        if root is None:  # pragma: no cover - only reached after _ensure_root
            return
        width = max((len(entry) for entry, _ in self._entries), default=0)
        lines = [
            "vaultspec-core snapshot",
            f"created:   {self._created.isoformat(sep=' ')}",
            f"operation: {self._label}",
            f"contents:  {self.files} file(s), {human_bytes(self._total_bytes)}",
            "",
            "These are byte-identical copies of documents vaultspec-core removed,",
            "taken immediately before the removal. Nothing deletes this directory",
            "automatically; delete it yourself once you no longer need it.",
            "",
            "To restore one, copy it back to the path on the right:",
            "",
        ]
        lines += [
            f"  {entry.ljust(width)}  ->  {origin}"
            for entry, origin in sorted(self._entries)
        ]
        lines.append("")
        try:
            (root / RESTORE_FILENAME).write_text("\n".join(lines), encoding="utf-8")
        except OSError as exc:
            self._abandon()
            raise SnapshotError(
                f"could not write {RESTORE_FILENAME} in {root}: {exc}"
            ) from exc

    def _abandon(self) -> None:
        """Drop a partial snapshot so a failed attempt leaves no half-copy.

        Best effort by design: the caller is already aborting, and a
        cleanup error must not replace the :class:`SnapshotError` that
        explains why nothing was deleted.
        """
        if self._root is None:
            return
        shutil.rmtree(self._root, ignore_errors=True)
        self._root = None
        self._entries.clear()
        self._total_bytes = 0


def snapshot_paths(
    workspace: Path, paths: Sequence[Path], *, label: str
) -> TrashSnapshot | None:
    """Snapshot *paths* in one shot and return the resulting directory.

    Convenience wrapper for callers that have their whole removal set at
    once. Callers that remove in batches should hold a :class:`TrashWriter`
    so every batch lands in one directory.

    Args:
        workspace: Workspace root directory.
        paths: Documents about to be deleted.
        label: Short slug naming the operation.

    Returns:
        The snapshot, or ``None`` when no path existed to copy.

    Raises:
        SnapshotError: When the snapshot could not be written; the caller
            must abort without deleting.
    """
    writer = TrashWriter(workspace, label)
    writer.capture(paths)
    return writer.result()
