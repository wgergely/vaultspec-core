"""Managed-block support for ``.gitignore`` files."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

MARKER_BEGIN = "# >>> vaultspec-managed (do not edit this block) >>>"
MARKER_END = "# <<< vaultspec-managed <<<"

# Internal state that must ALWAYS be ignored if gitignore is managed.
DEFAULT_ENTRIES = [".vaultspec/_snapshots/"]


def get_recommended_entries(target: Path) -> list[str]:
    """Return a list of gitignore entries for all managed paths.

    Uses :class:`~vaultspec_core.core.types.WorkspaceContext` and manifest
    data to dynamically discover provider directories and configuration files.
    """
    entries: set[str] = {".vaultspec/_snapshots/"}

    from .manifest import read_manifest_data

    try:
        mdata = read_manifest_data(target)
        # Always ignore framework internals if framework exists
        if (target / ".vaultspec").exists():
            entries.add(".vaultspec/")
        if (target / ".vault").exists():
            entries.add(".vault/")

        # Global files
        if (target / ".mcp.json").exists():
            entries.add(".mcp.json")

        # Use the canonical artifact collection logic from commands.py
        # to ensure gitignore is perfectly synced with provider artifacts.
        from .commands import _collect_provider_artifacts
        from .enums import Tool

        for name in mdata.installed:
            try:
                tool = Tool(name)
                dirs, files = _collect_provider_artifacts(target, tool)
                for d in dirs:
                    try:
                        rel_dir = d.relative_to(target)
                        entries.add(f"{str(rel_dir).replace('\\', '/')}/")
                    except ValueError:
                        pass
                for f in files:
                    try:
                        rel_file = f.relative_to(target)
                        entries.add(str(rel_file).replace("\\", "/"))
                    except ValueError:
                        pass
            except ValueError:
                continue

    except Exception:
        # Fallback for very early bootstrap or corruption
        pass

    return sorted(entries)


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
        stripped = line.rstrip()
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
    begins, ends = _find_markers(lines)

    if state == "absent":
        return _remove_block(gi_path, lines, begins, ends, eol, bom)
    return _add_block(gi_path, lines, begins, ends, entries, eol, bom)


def _add_block(
    gi_path: Path,
    lines: list[str],
    begins: list[int],
    ends: list[int],
    entries: list[str],
    eol: str,
    bom: bytes,
) -> bool:
    new_block = [MARKER_BEGIN, *entries, MARKER_END]

    # If we have exactly one block and it matches, do nothing.
    if len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0]:
        replaced = lines[: begins[0]] + new_block + lines[ends[0] + 1 :]
        if replaced == lines:
            return False

    # Otherwise, clean up all existing markers and append a fresh block.
    # Remove markers from end to start to avoid index shifts.
    to_pop = sorted(begins + ends, reverse=True)
    for idx in to_pop:
        lines.pop(idx)

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
    begins: list[int],
    ends: list[int],
    eol: str,
    bom: bytes,
) -> bool:
    if not begins and not ends:
        return False

    # If we have exactly one block, remove it and its contents.
    if len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0]:
        lines = lines[: begins[0]] + lines[ends[0] + 1 :]
    else:
        # For multiple or mismatched markers, just strip all markers.
        # Removing contents is risky if we can't reliably pair them.
        to_pop = sorted(begins + ends, reverse=True)
        for idx in to_pop:
            lines.pop(idx)

    lines = _collapse_double_blanks(lines)
    result = eol.join(lines) + eol
    _write(gi_path, result, bom)
    return True


def _write(gi_path: Path, content: str, bom: bytes) -> None:
    """Write *content* to *gi_path* atomically, restoring BOM if originally present.

    Uses a temporary file and rename to avoid partial writes.  Always
    writes in binary mode to preserve the caller-chosen line endings.
    Using text-mode would double ``\\r`` on Windows when the content
    already contains ``\\r\\n``.
    """
    payload = bom + content.encode("utf-8")
    tmp = gi_path.with_suffix(gi_path.suffix + f".{os.getpid()}.tmp")
    try:
        tmp.write_bytes(payload)
        try:
            tmp.replace(gi_path)
        except PermissionError:
            if os.name != "nt":
                raise
            try:
                shutil.copyfile(tmp, gi_path)
            finally:
                tmp.unlink(missing_ok=True)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
