"""A failed rollback must not truncate, and must not be a log line.

``RenameTransaction._rollback`` restores every snapshotted document as its last
act. It did so with ``Path.write_bytes``, which truncates the destination to
zero before writing, so an interruption inside the restore left a zero-length
``.md`` on the code path whose entire purpose is to prevent data loss. It then
caught ``OSError`` and continued after a ``logger.warning``, so a vault left in
a mixed state reported nothing at all (issue #456).

Every failure here is induced through the real filesystem - a read-only
destination, a directory planted where a document belongs - and every assertion
reads real bytes. No mocks, no patches.
"""

from __future__ import annotations

import contextlib
import os
import stat
from typing import TYPE_CHECKING

import pytest

from ..rename_engine import RenameTransaction, RollbackError, _safe_restore_bytes

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [pytest.mark.unit]

ORIGINAL = b"# the document\nthe rollback exists to bring these bytes back\n"


@pytest.fixture
def read_only_cleanup() -> Iterator[list[Path]]:
    """Restore the write bit on any path a test made read-only.

    ``tmp_path`` teardown cannot delete a read-only file on Windows, so the
    paths are handed back here rather than left for the fixture to trip over.
    """
    paths: list[Path] = []
    yield paths
    for path in paths:
        with contextlib.suppress(OSError):
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)


def _plant_hard_link(link: Path, target: Path) -> bool:
    """Plant a real second hard link to *target*, or prove the OS refuses.

    Follows the ``_plant_symlink`` idiom below: a real OS probe, never a
    runtime skip. Hard links need NTFS or a POSIX filesystem; a host that
    refuses one cannot host the scenario being modelled.

    Returns:
        ``True`` when the link was created, ``False`` when the OS refused.
    """
    try:
        os.link(target, link)
    except (OSError, NotImplementedError, AttributeError):
        assert not link.exists(), "refused hard link left an artifact behind"
        return False
    return True


def _plant_symlink(link: Path, target: Path) -> bool:
    """Plant a real OS symlink, or prove this host refuses symlink creation.

    Mirrors the ``_plant_symlink`` idiom in ``test_atomic_write`` and
    ``test_rename_feature_security``: a real OS probe, never a runtime skip.
    Windows refuses symlink creation without developer mode or elevation, and
    on such a host the scenario being modelled cannot exist.

    Returns:
        ``True`` when the symlink was created, ``False`` when the OS refused.
    """
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        assert not link.exists(), "refused symlink left an artifact behind"
        return False
    assert link.is_symlink()
    return True


class TestRestoreIsAtomic:
    def test_restore_replaces_rather_than_truncating_in_place(
        self, tmp_path: Path
    ) -> None:
        # A second hard link to the document is the deterministic witness of
        # which write semantics ran. ``Path.write_bytes`` opens the existing
        # file with O_TRUNC, so both names see the destination emptied and then
        # refilled - and an interruption between the two leaves a zero-length
        # document on the code path that exists to prevent data loss. An atomic
        # write builds the replacement elsewhere and renames it over the name,
        # so the witness still holds the pre-restore bytes afterwards. Timing a
        # kill would prove the same thing far less reliably: the page cache
        # absorbs a multi-megabyte write in under a millisecond.
        doc = tmp_path / "note.md"
        doc.write_bytes(b"bytes the failed operation wrote\n")
        witness = tmp_path / "witness.md"
        if not _plant_hard_link(witness, doc):
            return

        _safe_restore_bytes(doc, ORIGINAL)

        assert doc.read_bytes() == ORIGINAL
        assert witness.read_bytes() == b"bytes the failed operation wrote\n", (
            "the restore opened the destination in place and truncated it; "
            "an interruption there destroys the document being restored"
        )


class TestFailedRollbackRaises:
    def test_unrestorable_document_raises_rollback_error(
        self, tmp_path: Path, read_only_cleanup: list[Path]
    ) -> None:
        doc = tmp_path / "note.md"
        doc.write_bytes(ORIGINAL)
        read_only_cleanup.append(doc)

        with (
            pytest.raises(RollbackError) as caught,
            RenameTransaction(tmp_path) as tx,
        ):
            tx.snapshot([doc])
            doc.write_bytes(b"mutated by the failed operation\n")
            os.chmod(doc, stat.S_IREAD)
            raise RuntimeError("the operation failed")

        assert str(doc) in str(caught.value)
        assert caught.value.hint

    def test_rollback_error_preserves_the_original_failure(
        self, tmp_path: Path, read_only_cleanup: list[Path]
    ) -> None:
        # The operator has to learn two things: what failed, and that the
        # recovery from it also failed. Reporting only the second would hide
        # the cause; reporting only the first would hide the mixed vault.
        doc = tmp_path / "note.md"
        doc.write_bytes(ORIGINAL)
        read_only_cleanup.append(doc)

        with (
            pytest.raises(RollbackError) as caught,
            RenameTransaction(tmp_path) as tx,
        ):
            tx.snapshot([doc])
            doc.write_bytes(b"mutated by the failed operation\n")
            os.chmod(doc, stat.S_IREAD)
            raise RuntimeError("collision at the computed destination")

        assert isinstance(caught.value.__cause__, RuntimeError)
        assert "collision at the computed destination" in str(caught.value.__cause__)
        assert "collision at the computed destination" in str(caught.value), (
            "a plain-text renderer prints str(exc); the trigger has to be in it"
        )

    def test_every_restorable_document_is_still_restored(
        self, tmp_path: Path, read_only_cleanup: list[Path]
    ) -> None:
        # Aggregating rather than raising on the first failure is what keeps
        # one unrestorable path from stranding the documents behind it.
        blocked = tmp_path / "blocked.md"
        recoverable = tmp_path / "recoverable.md"
        for path in (blocked, recoverable):
            path.write_bytes(ORIGINAL)
        read_only_cleanup.append(blocked)

        with (
            pytest.raises(RollbackError) as caught,
            RenameTransaction(tmp_path) as tx,
        ):
            tx.snapshot([blocked, recoverable])
            blocked.write_bytes(b"mutated\n")
            recoverable.write_bytes(b"mutated\n")
            os.chmod(blocked, stat.S_IREAD)
            raise RuntimeError("the operation failed")

        assert recoverable.read_bytes() == ORIGINAL
        assert str(recoverable) not in str(caught.value)
        assert str(blocked) in str(caught.value)


class TestSuccessfulRollbackIsUnchanged:
    def test_clean_rollback_still_propagates_the_original(self, tmp_path: Path) -> None:
        doc = tmp_path / "note.md"
        doc.write_bytes(ORIGINAL)

        with (
            pytest.raises(RuntimeError, match="the operation failed"),
            RenameTransaction(tmp_path) as tx,
        ):
            tx.snapshot([doc])
            doc.write_bytes(b"mutated by the failed operation\n")
            raise RuntimeError("the operation failed")

        assert doc.read_bytes() == ORIGINAL

    def test_symlinked_target_is_restored_as_a_regular_file(
        self, tmp_path: Path
    ) -> None:
        doc = tmp_path / "note.md"
        doc.write_bytes(ORIGINAL)
        outside = tmp_path.parent / f"outside-{tmp_path.name}.md"
        outside.write_bytes(b"out of bounds\n")

        planted = False
        with (
            contextlib.suppress(RuntimeError),
            RenameTransaction(tmp_path) as tx,
        ):
            tx.snapshot([doc])
            doc.unlink()
            planted = _plant_symlink(doc, outside)
            raise RuntimeError("the operation failed")

        if not planted:
            # The host refuses symlinks, so the drift this models cannot
            # occur; the restore still has to put the bytes back.
            assert doc.read_bytes() == ORIGINAL
            return
        assert not doc.is_symlink()
        assert doc.read_bytes() == ORIGINAL
        assert outside.read_bytes() == b"out of bounds\n", (
            "the restore must never write through the link"
        )
