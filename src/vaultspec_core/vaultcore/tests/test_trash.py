"""Tests for the pre-deletion snapshot writer.

What must hold for the snapshot to be a safety net rather than a gesture:

- a copy is byte-identical to its original, including line endings and
  non-ASCII content, and lands at the original's vault-relative path;
- the copy exists before the original is unlinked, which the migration
  tests assert end to end and which is only possible because
  :meth:`TrashWriter.capture` completes before its caller deletes;
- a snapshot that cannot be written raises rather than returning quietly,
  and leaves no half-written directory behind;
- ``RESTORE.txt`` names every copy's origin, because "the files are sitting
  there" is only honest if the operator can tell which file was which.

Real temporary workspaces and real filesystem failures. No mocks, no
patches, no skips.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vaultspec_core.config import reset_config
from vaultspec_core.vaultcore.trash import (
    RESTORE_FILENAME,
    SnapshotError,
    TrashWriter,
    human_bytes,
    snapshot_paths,
    trash_root,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

pytestmark = [pytest.mark.unit]

_CRLF = b"---\r\ntags:\r\n  - '#exec'\r\n---\r\n\r\n# recordo\xc2\xa0brea\r\n"
_UTF8 = "# entrée\n\nDéjà vu — café.\n".encode()


@pytest.fixture(autouse=True)
def reset_cfg() -> Generator[None]:
    reset_config()
    yield
    reset_config()


def _doc(root: Path, relative: str, payload: bytes) -> Path:
    path = root / ".vault" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


class TestCopiesAreFaithful:
    def test_copy_is_byte_identical(self, tmp_path: Path) -> None:
        crlf = _doc(tmp_path, "exec/2026-05-17-demo/rec-a.md", _CRLF)
        utf8 = _doc(tmp_path, "research/2026-05-17-demo-research.md", _UTF8)

        snapshot = snapshot_paths(tmp_path, [crlf, utf8], label="probe")

        assert snapshot is not None
        assert snapshot.files == 2
        assert snapshot.total_bytes == len(_CRLF) + len(_UTF8)
        copied_crlf = snapshot.root / "exec" / "2026-05-17-demo" / "rec-a.md"
        copied_utf8 = snapshot.root / "research" / "2026-05-17-demo-research.md"
        assert copied_crlf.read_bytes() == _CRLF
        assert copied_utf8.read_bytes() == _UTF8

    def test_copy_keeps_its_vault_relative_path(self, tmp_path: Path) -> None:
        doc = _doc(tmp_path, "exec/2026-05-17-demo/rec-a.md", b"x\n")

        snapshot = snapshot_paths(tmp_path, [doc], label="probe")

        assert snapshot is not None
        assert snapshot.root.parent == trash_root(tmp_path)
        assert (snapshot.root / "exec" / "2026-05-17-demo" / "rec-a.md").is_file()

    def test_restore_index_names_every_origin(self, tmp_path: Path) -> None:
        first = _doc(tmp_path, "exec/2026-05-17-demo/rec-a.md", b"a\n")
        second = _doc(tmp_path, "exec/2026-05-17-demo/rec-b.md", b"bb\n")

        snapshot = snapshot_paths(tmp_path, [first, second], label="probe")

        assert snapshot is not None
        index = (snapshot.root / RESTORE_FILENAME).read_text(encoding="utf-8")
        assert ".vault/exec/2026-05-17-demo/rec-a.md" in index
        assert ".vault/exec/2026-05-17-demo/rec-b.md" in index
        assert "2 file(s)" in index

    def test_nothing_to_copy_leaves_no_directory(self, tmp_path: Path) -> None:
        (tmp_path / ".vault").mkdir()

        snapshot = snapshot_paths(
            tmp_path, [tmp_path / ".vault" / "absent.md"], label="probe"
        )

        assert snapshot is None
        assert not trash_root(tmp_path).exists()

    def test_two_writers_do_not_share_a_directory(self, tmp_path: Path) -> None:
        first = _doc(tmp_path, "exec/a.md", b"a\n")
        second = _doc(tmp_path, "exec/b.md", b"b\n")

        one = snapshot_paths(tmp_path, [first], label="probe")
        two = snapshot_paths(tmp_path, [second], label="probe")

        assert one is not None
        assert two is not None
        assert one.root != two.root
        assert (one.root / "exec" / "a.md").is_file()
        assert (two.root / "exec" / "b.md").is_file()


class TestRefusesRatherThanDegrades:
    def test_unwritable_trash_root_raises(self, tmp_path: Path) -> None:
        """A `.trash` that is a *file* is a real, portable write failure.

        The snapshot directory cannot be created beneath it, which is the
        same class of failure a full disk or a read-only `.vault/` produces
        and the one that must stop a migration rather than let it delete.
        """
        doc = _doc(tmp_path, "exec/a.md", b"a\n")
        trash_root(tmp_path).write_text("not a directory", encoding="utf-8")

        with pytest.raises(SnapshotError):
            snapshot_paths(tmp_path, [doc], label="probe")

        assert doc.read_bytes() == b"a\n"

    def test_a_failed_first_capture_leaves_no_directory(self, tmp_path: Path) -> None:
        """Nothing was committed, so the empty shell goes with the failure."""
        good = _doc(tmp_path, "exec/a.md", b"a\n")
        clash = _doc(tmp_path, "exec/b.md", b"b\n")
        writer = TrashWriter(tmp_path, "probe")
        # Resolve the directory so a destination inside it can be blocked
        # before the first capture commits anything to it. A directory where
        # a file must go defeats `shutil.copy2` on every platform.
        root = writer._ensure_root()
        (root / "exec" / "b.md").mkdir(parents=True)

        with pytest.raises(SnapshotError):
            writer.capture([good, clash])

        assert not root.exists()
        assert writer.result() is None
        assert good.read_bytes() == b"a\n"
        assert clash.read_bytes() == b"b\n"

    def test_a_failed_capture_keeps_the_copies_taken_before_it(
        self, tmp_path: Path
    ) -> None:
        """The invariant that stops a rollback from causing the loss.

        A migration folding several folders through one writer has already
        unlinked the earlier folder's records by the time a later folder
        fails. Discarding the whole directory to tidy up would destroy the
        only remaining copy of documents that are already gone.
        """
        good = _doc(tmp_path, "exec/a.md", b"a\n")
        clash = _doc(tmp_path, "exec/b.md", b"b\n")
        writer = TrashWriter(tmp_path, "probe")
        writer.capture([good])
        root = writer.root
        assert root is not None
        good.unlink()  # what every caller does after a successful capture
        (root / "exec" / "b.md").mkdir(parents=True)

        with pytest.raises(SnapshotError):
            writer.capture([clash])

        assert (root / "exec" / "a.md").read_bytes() == b"a\n", (
            "a rollback must not destroy an earlier batch's backups"
        )
        snapshot = writer.result()
        assert snapshot is not None
        assert snapshot.files == 1
        assert snapshot.total_bytes == 2
        assert clash.read_bytes() == b"b\n"

    def test_path_outside_the_workspace_is_refused(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        (workspace / ".vault").mkdir(parents=True)
        outsider = tmp_path / "elsewhere.md"
        outsider.write_text("x\n", encoding="utf-8")

        with pytest.raises(SnapshotError):
            snapshot_paths(workspace, [outsider], label="probe")

        assert outsider.exists()


class TestReporting:
    @pytest.mark.parametrize(
        ("count", "expected"),
        [(0, "0 B"), (512, "512 B"), (2048, "2.0 KB"), (5 * 1024 * 1024, "5.0 MB")],
    )
    def test_human_bytes(self, count: int, expected: str) -> None:
        assert human_bytes(count) == expected
