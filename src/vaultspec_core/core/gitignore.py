"""Managed-block support for ``.gitignore`` files."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MARKER_BEGIN = "# >>> vaultspec-managed (do not edit this block) >>>"
MARKER_END = "# <<< vaultspec-managed <<<"
DEFAULT_ENTRIES = [".vaultspec/_snapshots/"]


def _detect_line_ending(raw: bytes) -> str:
    """Return ``"\\r\\n"`` if CRLF is dominant in *raw*, else ``"\\n"``."""
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def _find_markers(lines: list[str]) -> tuple[int | None, int | None]:
    """Return ``(begin_index, end_index)`` of the managed block markers.

    Returns ``(None, None)`` when markers are duplicated or inverted,
    treating those cases as corruption (same as orphaned single marker).
    """
    begin: int | None = None
    end: int | None = None
    begin_count = 0
    end_count = 0
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if stripped == MARKER_BEGIN:
            begin_count += 1
            begin = i
        elif stripped == MARKER_END:
            end_count += 1
            end = i
    # Duplicates or inverted markers are treated as corruption.
    if begin_count > 1 or end_count > 1:
        return begin, None  # signal corruption via single-marker path
    if begin is not None and end is not None and begin > end:
        return begin, None  # inverted - treat as corruption
    return begin, end


def _collapse_double_blanks(lines: list[str]) -> list[str]:
    """Collapse consecutive blank lines into a single blank line."""
    result: list[str] = []
    prev_blank = False
    for line in lines:
        blank = line.strip() == ""
        if blank and prev_blank:
            continue
        result.append(line)
        prev_blank = blank
    return result


def ensure_gitignore_block(
    target: Path,
    entries: list[str],
    *,
    state: str = "present",
) -> bool:
    """Add or remove a vaultspec-managed block inside ``.gitignore``.

    The block is delimited by :data:`MARKER_BEGIN` / :data:`MARKER_END` and
    contains the caller-supplied *entries*.  The function is idempotent - it
    returns ``False`` when the file already matches the desired state.

    Args:
        target: Workspace root directory containing ``.gitignore``.
        entries: Gitignore patterns to manage inside the block.
        state: ``"present"`` to ensure the block exists, ``"absent"`` to
            remove it.

    Returns:
        ``True`` if the file was modified, ``False`` otherwise.
    """
    gi_path = target / ".gitignore"
    if not gi_path.exists():
        return False

    raw = gi_path.read_bytes()
    eol = _detect_line_ending(raw)

    # Preserve BOM if present.
    bom = b""
    text = raw
    if raw.startswith(b"\xef\xbb\xbf"):
        bom = b"\xef\xbb\xbf"
        text = raw[3:]

    content = text.decode("utf-8")
    lines = content.splitlines()
    begin, end = _find_markers(lines)

    try:
        if state == "absent":
            return _remove_block(gi_path, lines, begin, end, eol, bom)
        return _add_block(gi_path, lines, begin, end, entries, eol, bom)
    except OSError:
        logger.warning(
            "Could not write to %s (permission denied or read-only)", gi_path
        )
        return False


def _add_block(
    gi_path: Path,
    lines: list[str],
    begin: int | None,
    end: int | None,
    entries: list[str],
    eol: str,
    bom: bytes,
) -> bool:
    new_block = [MARKER_BEGIN, *entries, MARKER_END]

    if begin is not None and end is not None:
        # Replace existing block.
        replaced = lines[:begin] + new_block + lines[end + 1 :]
        if replaced == lines:
            return False
        result = eol.join(replaced) + eol
        _write(gi_path, result, bom)
        return True

    if begin is not None:
        logger.warning(
            "Removing orphaned gitignore marker at line %d in %s",
            begin + 1,
            gi_path,
        )
        lines.pop(begin)
    elif end is not None:
        logger.warning(
            "Removing orphaned gitignore marker at line %d in %s",
            end + 1,
            gi_path,
        )
        lines.pop(end)

    # Strip trailing blank lines, add separator, append block.
    while lines and lines[-1].strip() == "":
        lines.pop()
    lines.append("")
    lines.extend(new_block)

    result = eol.join(lines) + eol
    _write(gi_path, result, bom)
    return True


def _remove_block(
    gi_path: Path,
    lines: list[str],
    begin: int | None,
    end: int | None,
    eol: str,
    bom: bytes,
) -> bool:
    if begin is None and end is None:
        return False

    if begin is not None and end is not None:
        lines = lines[:begin] + lines[end + 1 :]
    elif begin is not None:
        lines.pop(begin)
    else:
        assert end is not None
        lines.pop(end)

    lines = _collapse_double_blanks(lines)
    result = eol.join(lines) + eol
    _write(gi_path, result, bom)
    return True


def _write(gi_path: Path, content: str, bom: bytes) -> None:
    """Write *content* to *gi_path*, restoring BOM if originally present.

    Always writes in binary mode to preserve the caller-chosen line
    endings.  Using text-mode would double ``\\r`` on Windows when the
    content already contains ``\\r\\n``.
    """
    gi_path.write_bytes(bom + content.encode("utf-8"))
