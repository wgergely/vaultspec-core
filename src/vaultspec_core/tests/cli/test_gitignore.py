"""Tests for the gitignore managed-block module."""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.core.enums import ManagedState
from vaultspec_core.core.gitignore import (
    MARKER_BEGIN,
    MARKER_END,
    _find_markers,
    ensure_gitignore_block,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]

ENTRIES = [".vaultspec/_snapshots/"]


def _gi(root: Path) -> Path:
    return root / ".gitignore"


def _write_gi(root: Path, content: str, *, binary: bool = False) -> None:
    path = _gi(root)
    if binary:
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
    else:
        path.write_text(content, encoding="utf-8")


def _read_gi(root: Path) -> str:
    return _gi(root).read_text(encoding="utf-8")


class TestBlockInsertion:
    def test_insert_into_existing_gitignore(self, tmp_path):
        _write_gi(tmp_path, "node_modules/\n")
        changed = ensure_gitignore_block(tmp_path, ENTRIES)

        assert changed is True
        text = _read_gi(tmp_path)
        assert MARKER_BEGIN in text
        assert MARKER_END in text
        assert ".vaultspec/_snapshots/" in text
        assert text.startswith("node_modules/")

    def test_no_gitignore_returns_false(self, tmp_path):
        changed = ensure_gitignore_block(tmp_path, ENTRIES)
        assert changed is False

    def test_empty_gitignore(self, tmp_path):
        _write_gi(tmp_path, "")
        changed = ensure_gitignore_block(tmp_path, ENTRIES)

        assert changed is True
        text = _read_gi(tmp_path)
        assert MARKER_BEGIN in text
        assert ENTRIES[0] in text


class TestBlockUpdate:
    def test_update_existing_block(self, tmp_path):
        _write_gi(tmp_path, "node_modules/\n")
        ensure_gitignore_block(tmp_path, ENTRIES)
        new_entries = [".vaultspec/_snapshots/", ".vaultspec/cache/"]
        changed = ensure_gitignore_block(tmp_path, new_entries)

        assert changed is True
        text = _read_gi(tmp_path)
        assert ".vaultspec/cache/" in text
        assert text.count(MARKER_BEGIN) == 1
        assert text.count(MARKER_END) == 1


class TestBlockRemoval:
    def test_remove_existing_block(self, tmp_path):
        _write_gi(tmp_path, "node_modules/\n")
        ensure_gitignore_block(tmp_path, ENTRIES)
        changed = ensure_gitignore_block(tmp_path, ENTRIES, state=ManagedState.ABSENT)

        assert changed is True
        text = _read_gi(tmp_path)
        assert MARKER_BEGIN not in text
        assert MARKER_END not in text

    def test_remove_no_block_returns_false(self, tmp_path):
        _write_gi(tmp_path, "node_modules/\n")
        changed = ensure_gitignore_block(tmp_path, ENTRIES, state=ManagedState.ABSENT)
        assert changed is False


class TestIdempotency:
    def test_same_entries_twice_returns_false(self, tmp_path):
        _write_gi(tmp_path, "node_modules/\n")
        ensure_gitignore_block(tmp_path, ENTRIES)
        changed = ensure_gitignore_block(tmp_path, ENTRIES)
        assert changed is False

    def test_content_stable_after_two_calls(self, tmp_path):
        _write_gi(tmp_path, "node_modules/\n")
        ensure_gitignore_block(tmp_path, ENTRIES)
        content_after_first = _gi(tmp_path).read_bytes()
        ensure_gitignore_block(tmp_path, ENTRIES)
        content_after_second = _gi(tmp_path).read_bytes()
        assert content_after_first == content_after_second


class TestOrphanedMarkers:
    def test_orphaned_begin_marker(self, tmp_path):
        content = f"node_modules/\n{MARKER_BEGIN}\n.vaultspec/_snapshots/\n"
        _write_gi(tmp_path, content)
        changed = ensure_gitignore_block(tmp_path, ENTRIES)

        assert changed is True
        text = _read_gi(tmp_path)
        assert text.count(MARKER_BEGIN) == 1
        assert text.count(MARKER_END) == 1

    def test_orphaned_end_marker(self, tmp_path):
        content = f"node_modules/\n{MARKER_END}\n"
        _write_gi(tmp_path, content)
        changed = ensure_gitignore_block(tmp_path, ENTRIES)

        assert changed is True
        text = _read_gi(tmp_path)
        assert text.count(MARKER_BEGIN) == 1
        assert text.count(MARKER_END) == 1


class TestLineEndings:
    def test_crlf_preserved(self, tmp_path):
        raw = b"node_modules/\r\n.env\r\n"
        _gi(tmp_path).write_bytes(raw)
        ensure_gitignore_block(tmp_path, ENTRIES)

        result = _gi(tmp_path).read_bytes()
        # CRLF should be dominant in the output
        crlf_count = result.count(b"\r\n")
        lf_only = result.count(b"\n") - crlf_count
        assert crlf_count > lf_only


class TestContentPreservation:
    def test_user_content_above_and_below(self, tmp_path):
        before_block = "# user content above\nnode_modules/\n"
        block = f"{MARKER_BEGIN}\n.old_entry/\n{MARKER_END}\n"
        after_block = "# user content below\n.env\n"
        _write_gi(tmp_path, before_block + block + after_block)

        ensure_gitignore_block(tmp_path, ENTRIES)

        text = _read_gi(tmp_path)
        assert "# user content above" in text
        assert "node_modules/" in text
        assert "# user content below" in text
        assert ".env" in text
        assert ".vaultspec/_snapshots/" in text


class TestTrailingBlanks:
    def test_multiple_trailing_blanks_normalized(self, tmp_path):
        _write_gi(tmp_path, "node_modules/\n\n\n\n")
        ensure_gitignore_block(tmp_path, ENTRIES)

        text = _read_gi(tmp_path)
        # Between user content and block there should be at most one blank line
        lines = text.split("\n")
        consecutive_blanks = 0
        max_blanks = 0
        for line in lines:
            if line.strip() == "":
                consecutive_blanks += 1
                max_blanks = max(max_blanks, consecutive_blanks)
            else:
                consecutive_blanks = 0
        assert max_blanks <= 1


class TestFileWithoutNewline:
    def test_file_ending_without_newline(self, tmp_path):
        _write_gi(tmp_path, "node_modules/")
        changed = ensure_gitignore_block(tmp_path, ENTRIES)

        assert changed is True
        text = _read_gi(tmp_path)
        assert MARKER_BEGIN in text
        assert text.endswith("\n")


class TestInvertedMarkers:
    def test_find_markers_inverted_returns_both(self):
        lines = ["some content", MARKER_END, ".entry/", MARKER_BEGIN]
        begins, ends = _find_markers(lines)
        assert begins == [3]
        assert ends == [1]

    def test_ensure_removes_both_markers_and_appends_fresh_block(self, tmp_path):
        content = f"node_modules/\n{MARKER_END}\n.entry/\n{MARKER_BEGIN}\n"
        _write_gi(tmp_path, content)
        changed = ensure_gitignore_block(tmp_path, ENTRIES)

        assert changed is True
        text = _read_gi(tmp_path)
        # All existing markers (begin and end) are removed; a fresh block is appended.
        assert text.count(MARKER_BEGIN) == 1
        assert text.count(MARKER_END) == 1
        assert text.endswith(f"{MARKER_END}\n")


class TestDuplicateBeginMarkers:
    def test_find_markers_duplicate_begin_returns_all(self):
        lines = [MARKER_BEGIN, ".entry/", MARKER_BEGIN, ".entry2/", MARKER_END]
        begins, ends = _find_markers(lines)
        assert begins == [0, 2]
        assert ends == [4]

    def test_ensure_handles_duplicate_begin(self, tmp_path):
        content = f"{MARKER_BEGIN}\n.entry/\n{MARKER_BEGIN}\n.entry2/\n{MARKER_END}\n"
        _write_gi(tmp_path, content)
        changed = ensure_gitignore_block(tmp_path, ENTRIES)

        assert changed is True
        text = _read_gi(tmp_path)
        # ALL duplicate markers are removed; a fresh clean block is appended.
        assert text.count(MARKER_BEGIN) == 1
        assert text.count(MARKER_END) == 1


class TestDuplicateEndMarkers:
    def test_find_markers_duplicate_end_returns_all(self):
        lines = [MARKER_BEGIN, ".entry/", MARKER_END, MARKER_END]
        begins, ends = _find_markers(lines)
        assert begins == [0]
        assert ends == [2, 3]

    def test_ensure_handles_duplicate_end(self, tmp_path):
        content = f"{MARKER_BEGIN}\n.entry/\n{MARKER_END}\n{MARKER_END}\n"
        _write_gi(tmp_path, content)
        changed = ensure_gitignore_block(tmp_path, ENTRIES)

        assert changed is True
        text = _read_gi(tmp_path)
        # ALL duplicate markers are removed; a fresh clean block is appended.
        assert text.count(MARKER_BEGIN) == 1
        assert text.count(MARKER_END) == 1


class TestEmptyEntriesList:
    def test_empty_entries_writes_markers_only(self, tmp_path):
        _write_gi(tmp_path, "node_modules/\n")
        changed = ensure_gitignore_block(tmp_path, [], state=ManagedState.PRESENT)

        assert changed is True
        text = _read_gi(tmp_path)
        assert MARKER_BEGIN in text
        assert MARKER_END in text
        # Nothing between markers
        lines = text.splitlines()
        begin_idx = next(i for i, ln in enumerate(lines) if ln.rstrip() == MARKER_BEGIN)
        end_idx = next(i for i, ln in enumerate(lines) if ln.rstrip() == MARKER_END)
        assert end_idx == begin_idx + 1


class TestReadOnlyGitignore:
    def test_read_only_raises_oserror(self, tmp_path):
        _write_gi(tmp_path, "node_modules/\n")
        gi = _gi(tmp_path)
        gi.chmod(stat.S_IREAD)
        try:
            # On Linux, root/CI can write read-only files; also, atomic
            # replace (rename) can succeed for 0444 files if the directory is
            # writable. Verify the guard works only when the OS actually
            # enforces it for the specific mechanism we use.
            try:
                probe = tmp_path / "probe.tmp"
                probe.write_bytes(b"test")
                try:
                    probe.replace(gi)
                    can_write = True
                except OSError:
                    can_write = False
                finally:
                    probe.unlink(missing_ok=True)
            except OSError:
                can_write = False
            finally:
                # Restore original state if probe replaced it
                if can_write:
                    _write_gi(tmp_path, "node_modules/\n")
                    gi.chmod(stat.S_IREAD)

            if can_write:
                # OS did not enforce read-only; just verify no crash
                ensure_gitignore_block(tmp_path, ENTRIES)
                gi.write_bytes(b"node_modules/\n")
            else:
                with pytest.raises(OSError):
                    ensure_gitignore_block(tmp_path, ENTRIES)
        finally:
            gi.chmod(stat.S_IREAD | stat.S_IWRITE)
