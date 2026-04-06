"""Tests for the gitattributes managed-block module."""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.core.enums import ManagedState
from vaultspec_core.core.gitattributes import (
    DEFAULT_ENTRIES,
    MARKER_BEGIN,
    MARKER_END,
    _find_markers,
    ensure_gitattributes_block,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]


def _ga(root: Path) -> Path:
    return root / ".gitattributes"


def _write_ga(root: Path, content: str, *, binary: bool = False) -> None:
    path = _ga(root)
    if binary:
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
    else:
        path.write_text(content, encoding="utf-8")


def _read_ga(root: Path) -> str:
    return _ga(root).read_text(encoding="utf-8")


class TestFileCreation:
    def test_creates_file_when_missing(self, tmp_path):
        changed = ensure_gitattributes_block(tmp_path)

        assert changed is True
        assert _ga(tmp_path).exists()
        text = _read_ga(tmp_path)
        assert MARKER_BEGIN in text
        assert MARKER_END in text
        for entry in DEFAULT_ENTRIES:
            assert entry in text

    def test_absent_state_no_file_returns_false(self, tmp_path):
        changed = ensure_gitattributes_block(tmp_path, state=ManagedState.ABSENT)
        assert changed is False
        assert not _ga(tmp_path).exists()


class TestBlockInsertion:
    def test_insert_into_existing_gitattributes(self, tmp_path):
        _write_ga(tmp_path, "*.jpg binary\n")
        changed = ensure_gitattributes_block(tmp_path)

        assert changed is True
        text = _read_ga(tmp_path)
        assert MARKER_BEGIN in text
        assert MARKER_END in text
        assert "* text=auto eol=lf" in text
        assert text.startswith("*.jpg binary")

    def test_empty_gitattributes(self, tmp_path):
        _write_ga(tmp_path, "")
        changed = ensure_gitattributes_block(tmp_path)

        assert changed is True
        text = _read_ga(tmp_path)
        assert MARKER_BEGIN in text
        assert DEFAULT_ENTRIES[0] in text


class TestBlockUpdate:
    def test_update_existing_block(self, tmp_path):
        _write_ga(tmp_path, "*.jpg binary\n")
        ensure_gitattributes_block(tmp_path)
        new_entries = ["* text=auto eol=lf", "*.ps1 text eol=crlf"]
        changed = ensure_gitattributes_block(tmp_path, new_entries)

        assert changed is True
        text = _read_ga(tmp_path)
        assert "*.ps1 text eol=crlf" in text
        assert text.count(MARKER_BEGIN) == 1
        assert text.count(MARKER_END) == 1


class TestBlockRemoval:
    def test_remove_existing_block(self, tmp_path):
        _write_ga(tmp_path, "*.jpg binary\n")
        ensure_gitattributes_block(tmp_path)
        changed = ensure_gitattributes_block(tmp_path, state=ManagedState.ABSENT)

        assert changed is True
        text = _read_ga(tmp_path)
        assert MARKER_BEGIN not in text
        assert MARKER_END not in text

    def test_remove_no_block_returns_false(self, tmp_path):
        _write_ga(tmp_path, "*.jpg binary\n")
        changed = ensure_gitattributes_block(tmp_path, state=ManagedState.ABSENT)
        assert changed is False


class TestIdempotency:
    def test_same_entries_twice_returns_false(self, tmp_path):
        _write_ga(tmp_path, "*.jpg binary\n")
        ensure_gitattributes_block(tmp_path)
        changed = ensure_gitattributes_block(tmp_path)
        assert changed is False

    def test_content_stable_after_two_calls(self, tmp_path):
        _write_ga(tmp_path, "*.jpg binary\n")
        ensure_gitattributes_block(tmp_path)
        content_after_first = _ga(tmp_path).read_bytes()
        ensure_gitattributes_block(tmp_path)
        content_after_second = _ga(tmp_path).read_bytes()
        assert content_after_first == content_after_second


class TestOrphanedMarkers:
    def test_orphaned_begin_marker(self, tmp_path):
        content = f"*.jpg binary\n{MARKER_BEGIN}\n* text=auto eol=lf\n"
        _write_ga(tmp_path, content)
        changed = ensure_gitattributes_block(tmp_path)

        assert changed is True
        text = _read_ga(tmp_path)
        assert text.count(MARKER_BEGIN) == 1
        assert text.count(MARKER_END) == 1

    def test_orphaned_end_marker(self, tmp_path):
        content = f"*.jpg binary\n{MARKER_END}\n"
        _write_ga(tmp_path, content)
        changed = ensure_gitattributes_block(tmp_path)

        assert changed is True
        text = _read_ga(tmp_path)
        assert text.count(MARKER_BEGIN) == 1
        assert text.count(MARKER_END) == 1


class TestLineEndings:
    def test_crlf_preserved(self, tmp_path):
        raw = b"*.jpg binary\r\n*.png binary\r\n"
        _ga(tmp_path).write_bytes(raw)
        ensure_gitattributes_block(tmp_path)

        result = _ga(tmp_path).read_bytes()
        crlf_count = result.count(b"\r\n")
        lf_only = result.count(b"\n") - crlf_count
        assert crlf_count > lf_only

    def test_created_file_uses_lf(self, tmp_path):
        ensure_gitattributes_block(tmp_path)
        raw = _ga(tmp_path).read_bytes()
        assert b"\r\n" not in raw
        assert b"\n" in raw


class TestContentPreservation:
    def test_user_content_above_and_below(self, tmp_path):
        before_block = "# user content above\n*.jpg binary\n"
        block = f"{MARKER_BEGIN}\n*.old entry\n{MARKER_END}\n"
        after_block = "# user content below\n*.png binary\n"
        _write_ga(tmp_path, before_block + block + after_block)

        ensure_gitattributes_block(tmp_path)

        text = _read_ga(tmp_path)
        assert "# user content above" in text
        assert "*.jpg binary" in text
        assert "# user content below" in text
        assert "*.png binary" in text
        assert "* text=auto eol=lf" in text


class TestTrailingBlanks:
    def test_multiple_trailing_blanks_normalized(self, tmp_path):
        _write_ga(tmp_path, "*.jpg binary\n\n\n\n")
        ensure_gitattributes_block(tmp_path)

        text = _read_ga(tmp_path)
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
        _write_ga(tmp_path, "*.jpg binary")
        changed = ensure_gitattributes_block(tmp_path)

        assert changed is True
        text = _read_ga(tmp_path)
        assert MARKER_BEGIN in text
        assert text.endswith("\n")


class TestInvertedMarkers:
    def test_find_markers_inverted_returns_both(self):
        lines = ["some content", MARKER_END, "*.entry", MARKER_BEGIN]
        begins, ends = _find_markers(lines)
        assert begins == [3]
        assert ends == [1]

    def test_ensure_removes_both_markers_and_appends_fresh_block(self, tmp_path):
        content = f"*.jpg binary\n{MARKER_END}\n*.entry\n{MARKER_BEGIN}\n"
        _write_ga(tmp_path, content)
        changed = ensure_gitattributes_block(tmp_path)

        assert changed is True
        text = _read_ga(tmp_path)
        assert text.count(MARKER_BEGIN) == 1
        assert text.count(MARKER_END) == 1
        assert text.endswith(f"{MARKER_END}\n")


class TestDuplicateBeginMarkers:
    def test_ensure_handles_duplicate_begin(self, tmp_path):
        content = f"{MARKER_BEGIN}\n*.entry\n{MARKER_BEGIN}\n*.entry2\n{MARKER_END}\n"
        _write_ga(tmp_path, content)
        changed = ensure_gitattributes_block(tmp_path)

        assert changed is True
        text = _read_ga(tmp_path)
        assert text.count(MARKER_BEGIN) == 1
        assert text.count(MARKER_END) == 1


class TestDuplicateEndMarkers:
    def test_ensure_handles_duplicate_end(self, tmp_path):
        content = f"{MARKER_BEGIN}\n*.entry\n{MARKER_END}\n{MARKER_END}\n"
        _write_ga(tmp_path, content)
        changed = ensure_gitattributes_block(tmp_path)

        assert changed is True
        text = _read_ga(tmp_path)
        assert text.count(MARKER_BEGIN) == 1
        assert text.count(MARKER_END) == 1


class TestEmptyEntriesList:
    def test_empty_entries_writes_markers_only(self, tmp_path):
        _write_ga(tmp_path, "*.jpg binary\n")
        changed = ensure_gitattributes_block(tmp_path, [], state=ManagedState.PRESENT)

        assert changed is True
        text = _read_ga(tmp_path)
        assert MARKER_BEGIN in text
        assert MARKER_END in text
        lines = text.splitlines()
        begin_idx = next(i for i, ln in enumerate(lines) if ln.rstrip() == MARKER_BEGIN)
        end_idx = next(i for i, ln in enumerate(lines) if ln.rstrip() == MARKER_END)
        assert end_idx == begin_idx + 1


class TestReadOnlyGitattributes:
    def test_read_only_raises_oserror(self, tmp_path):
        _write_ga(tmp_path, "*.jpg binary\n")
        ga = _ga(tmp_path)
        ga.chmod(stat.S_IREAD)
        try:
            try:
                probe = tmp_path / "probe.tmp"
                probe.write_bytes(b"test")
                try:
                    probe.replace(ga)
                    can_write = True
                except OSError:
                    can_write = False
                finally:
                    probe.unlink(missing_ok=True)
            except OSError:
                can_write = False
            finally:
                if can_write:
                    _write_ga(tmp_path, "*.jpg binary\n")
                    ga.chmod(stat.S_IREAD)

            if can_write:
                ensure_gitattributes_block(tmp_path)
                ga.write_bytes(b"*.jpg binary\n")
            else:
                with pytest.raises(OSError):
                    ensure_gitattributes_block(tmp_path)
        finally:
            ga.chmod(stat.S_IREAD | stat.S_IWRITE)
