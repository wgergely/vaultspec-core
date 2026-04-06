"""Managed-block support for ``.gitattributes`` files.

Mirrors the :mod:`~vaultspec_core.core.gitignore` managed-block pattern
to enforce consistent line endings across the ecosystem.  The default
template normalises text to LF and exempts Windows batch files.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from .enums import ManagedState

logger = logging.getLogger(__name__)

MARKER_BEGIN = "# >>> vaultspec-managed (do not edit this block) >>>"
MARKER_END = "# <<< vaultspec-managed <<<"

DEFAULT_ENTRIES = [
    "* text=auto eol=lf",
    "*.bat text eol=crlf",
    "*.cmd text eol=crlf",
]


def has_valid_block(lines: list[str]) -> bool:
    """Return ``True`` if *lines* contain exactly one well-formed managed block.

    A valid block has exactly one :data:`MARKER_BEGIN` followed by exactly
    one :data:`MARKER_END`.

    Args:
        lines: Splitlines of the file content.

    Returns:
        ``True`` when the block structure is valid.
    """
    begins, ends = _find_markers(lines)
    return len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0]


def ensure_gitattributes_block(
    target: Path,
    entries: list[str] | None = None,
    *,
    state: ManagedState = ManagedState.PRESENT,
) -> bool:
    """Add or remove a vaultspec-managed block inside ``.gitattributes``.

    Unlike :func:`~vaultspec_core.core.gitignore.ensure_gitignore_block`,
    this function **creates** the file when it does not exist and *state*
    is :attr:`~vaultspec_core.core.enums.ManagedState.PRESENT`.

    Args:
        target: Workspace root directory containing ``.gitattributes``.
        entries: Attribute patterns to manage inside the block.  Defaults
            to :data:`DEFAULT_ENTRIES` when ``None``.
        state: Desired state (PRESENT or ABSENT).

    Returns:
        ``True`` if the file was created or modified, ``False`` otherwise.
    """
    if entries is None:
        entries = list(DEFAULT_ENTRIES)

    ga_path = target / ".gitattributes"

    if not ga_path.exists():
        if state == ManagedState.ABSENT:
            return False
        # Create the file with the managed block.
        new_block = [MARKER_BEGIN, *entries, MARKER_END]
        content = "\n".join(new_block) + "\n"
        _write(ga_path, content, b"")
        return True

    raw = ga_path.read_bytes()
    eol = _detect_line_ending(raw)

    # Preserve BOM if present.
    bom = b""
    text = raw
    if raw.startswith(b"\xef\xbb\xbf"):
        bom = b"\xef\xbb\xbf"
        text = raw[3:]

    content = text.decode("utf-8")
    lines = content.splitlines()
    begins, ends = _find_markers(lines)

    if state == ManagedState.ABSENT:
        return _remove_block(ga_path, lines, begins, ends, eol, bom)
    return _add_block(ga_path, lines, begins, ends, entries, eol, bom)


def _detect_line_ending(raw: bytes) -> str:
    """Return ``"\\r\\n"`` if CRLF is dominant in *raw*, else ``"\\n"``."""
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def _find_markers(lines: list[str]) -> tuple[list[int], list[int]]:
    """Return ``(begin_indices, end_indices)`` of the managed block markers."""
    begins: list[int] = []
    ends: list[int] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == MARKER_BEGIN:
            begins.append(i)
        elif stripped == MARKER_END:
            ends.append(i)
    return begins, ends


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


def _purge_markers(
    lines: list[str],
    begins: list[int],
    ends: list[int],
) -> None:
    """Remove all managed-block markers and their content from *lines* in-place.

    Pairs begin/end markers using a stack, removes paired ranges from end
    to start to avoid index shifts, then removes any orphaned markers.
    """
    ranges: list[tuple[int, int]] = []
    stack: list[int] = []
    marker_indices = sorted(
        [(i, "B") for i in begins] + [(i, "E") for i in ends], key=lambda x: x[0]
    )
    for idx, mtype in marker_indices:
        if mtype == "B":
            stack.append(idx)
        elif mtype == "E" and stack:
            start = stack.pop()
            ranges.append((start, idx))

    if ranges:
        for start, end in sorted(ranges, key=lambda x: x[0], reverse=True):
            lines[start : end + 1] = []

        begins_left, ends_left = _find_markers(lines)
        to_pop = sorted(begins_left + ends_left, reverse=True)
        for idx in to_pop:
            lines.pop(idx)
    else:
        to_pop = sorted(begins + ends, reverse=True)
        for idx in to_pop:
            lines.pop(idx)


def _add_block(
    ga_path: Path,
    lines: list[str],
    begins: list[int],
    ends: list[int],
    entries: list[str],
    eol: str,
    bom: bytes,
) -> bool:
    """Add or update the vaultspec-managed block in-place."""
    new_block = [MARKER_BEGIN, *entries, MARKER_END]

    # If we have exactly one block, update it in-place.
    if len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0]:
        replaced = lines[: begins[0]] + new_block + lines[ends[0] + 1 :]
        if replaced == lines:
            return False
        result = eol.join(replaced) + eol
        _write(ga_path, result, bom)
        return True

    # Otherwise, clean up all existing markers and content between them.
    _purge_markers(lines, begins, ends)

    # Strip trailing blank lines, add separator, append block.
    while lines and lines[-1].strip() == "":
        lines.pop()
    if lines:
        lines.append("")
    lines.extend(new_block)

    result = eol.join(lines) + eol
    _write(ga_path, result, bom)
    return True


def _remove_block(
    ga_path: Path,
    lines: list[str],
    begins: list[int],
    ends: list[int],
    eol: str,
    bom: bytes,
) -> bool:
    if not begins and not ends:
        return False

    if len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0]:
        lines = lines[: begins[0]] + lines[ends[0] + 1 :]
    else:
        _purge_markers(lines, begins, ends)

    lines = _collapse_double_blanks(lines)
    result = eol.join(lines) + eol
    _write(ga_path, result, bom)
    return True


def _write(ga_path: Path, content: str, bom: bytes) -> None:
    """Write *content* to *ga_path* atomically, restoring BOM if originally present.

    Always writes in binary mode to preserve the caller-chosen line endings.
    """
    payload = bom + content.encode("utf-8")
    tmp = ga_path.with_suffix(ga_path.suffix + f".{os.getpid()}.tmp")
    try:
        tmp.write_bytes(payload)
        try:
            tmp.replace(ga_path)
        except PermissionError:
            if os.name != "nt":
                raise
            try:
                shutil.copyfile(tmp, ga_path)
            finally:
                tmp.unlink(missing_ok=True)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
