"""Parse, insert, update, and remove ``<vaultspec>`` managed content blocks.

Managed blocks allow vaultspec to own a section of a file while
preserving user-authored content outside the block.  The tag format is::

    <vaultspec type="config">
    Managed content here.
    </vaultspec>

For TOML files, tags are wrapped in comments::

    # <vaultspec type="config">
    managed_key = "value"
    # </vaultspec>

Error handling is strict: malformed tag states (orphaned, duplicated,
nested) produce a :class:`TagError` with line numbers.  The parser
never auto-fixes and never crashes — callers decide how to surface
the error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Patterns for matching opening and closing tags.
# Opening: <vaultspec type="TYPE"> or # <vaultspec type="TYPE">
_OPEN_RE = re.compile(
    r'^(?P<prefix>#\s*)?<vaultspec\s+type="(?P<type>[^"]+)"[^>]*>\s*$'
)
# Closing: </vaultspec> or # </vaultspec>
_CLOSE_RE = re.compile(r"^(?P<prefix>#\s*)?</vaultspec>\s*$")

# Code fence detection (``` or ~~~, optionally with language tag).
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")


class TagError(Exception):
    """Raised when ``<vaultspec>`` managed tags are in an invalid state.

    Attributes:
        line: 1-based line number where the error was detected, or ``None``
            if not applicable.
    """

    def __init__(self, message: str, line: int | None = None) -> None:
        self.line = line
        super().__init__(message)


@dataclass
class TagBlock:
    """Location of a parsed ``<vaultspec>`` managed block within file content.

    All line numbers are 1-based (matching editor conventions).

    Attributes:
        block_type: The ``type`` attribute value (e.g. ``"config"``).
        start_line: Line number of the opening ``<vaultspec>`` tag.
        end_line: Line number of the closing ``</vaultspec>`` tag.
        content_start: First line of the block body (line after opening tag).
        content_end: Last line of the block body (line before closing tag).
    """

    block_type: str
    start_line: int
    end_line: int
    content_start: int
    content_end: int


def _is_inside_fence(fence_state: str | None) -> bool:
    return fence_state is not None


def find_blocks(content: str) -> list[TagBlock]:
    """Find all ``<vaultspec>`` blocks in *content*.

    Skips tags inside fenced code blocks (``` or ~~~).
    Orphaned closing tags are silently ignored.

    Args:
        content: Full file content to parse.

    Returns:
        List of :class:`TagBlock` instances in document order.

    Raises:
        TagError: On unclosed opening tags, duplicate block types, or nested
            ``<vaultspec>`` tags.
    """
    lines = content.splitlines()
    blocks: list[TagBlock] = []
    seen_types: dict[str, int] = {}
    open_tag: tuple[str, int] | None = None  # (type, line_number)
    fence: str | None = None

    for i, line in enumerate(lines):
        lineno = i + 1
        stripped = line.strip()

        # Track fenced code blocks.
        fence_match = _FENCE_RE.match(stripped)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker[0]  # track which char opened the fence
            elif stripped.startswith(fence):
                fence = None
            continue

        if _is_inside_fence(fence):
            continue

        # Check for opening tag.
        open_match = _OPEN_RE.match(stripped)
        if open_match:
            block_type = open_match.group("type")

            if open_tag is not None:
                raise TagError(
                    f"Nested <vaultspec> at line {lineno} inside "
                    f"block opened at line {open_tag[1]}",
                    line=lineno,
                )

            if block_type in seen_types:
                raise TagError(
                    f'Duplicate <vaultspec type="{block_type}"> '
                    f"at lines {seen_types[block_type]} and {lineno}",
                    line=lineno,
                )

            open_tag = (block_type, lineno)
            continue

        # Check for closing tag.
        close_match = _CLOSE_RE.match(stripped)
        if close_match:
            if open_tag is None:
                # Orphaned closing tag — ignore per contract.
                continue

            block_type, start = open_tag
            blocks.append(
                TagBlock(
                    block_type=block_type,
                    start_line=start,
                    end_line=lineno,
                    content_start=start + 1,
                    content_end=lineno - 1,
                )
            )
            seen_types[block_type] = start
            open_tag = None

    if open_tag is not None:
        raise TagError(
            f'Unclosed <vaultspec type="{open_tag[0]}"> at line {open_tag[1]}',
            line=open_tag[1],
        )

    return blocks


def has_block(content: str, block_type: str) -> bool:
    """Return ``True`` if *content* contains a managed block of *block_type*.

    Returns ``False`` (rather than raising) when tags are malformed.

    Args:
        content: Full file content to search.
        block_type: The ``type`` attribute to look for (e.g. ``"config"``).

    Returns:
        ``True`` if a block with the given type exists.
    """
    try:
        return any(b.block_type == block_type for b in find_blocks(content))
    except TagError:
        return False


def get_block_content(content: str, block_type: str) -> str | None:
    """Extract the inner content of a managed block.

    Args:
        content: Full file content to search.
        block_type: The ``type`` attribute to look for.

    Returns:
        Block body as a string (may be empty string for an empty block),
        or ``None`` if no block of the given type exists.

    Raises:
        TagError: If the file has malformed tags.
    """
    blocks = find_blocks(content)
    lines = content.splitlines()
    for b in blocks:
        if b.block_type == block_type:
            if b.content_start > b.content_end:
                return ""
            return "\n".join(lines[b.content_start - 1 : b.content_end])
    return None


def upsert_block(
    content: str,
    block_type: str,
    block_content: str,
    comment_prefix: str = "",
) -> str:
    """Insert or replace a managed block in *content*.

    Args:
        content: The full file content.
        block_type: The ``type`` attribute value (e.g. ``"config"``).
        block_content: The new content to place between the tags.
        comment_prefix: Prefix for the tags (e.g. ``"# "`` for TOML).

    Returns:
        The updated file content.

    Raises:
        TagError: If the file has malformed tags.
    """
    open_tag = f'{comment_prefix}<vaultspec type="{block_type}">'
    close_tag = f"{comment_prefix}</vaultspec>"
    lines = content.splitlines()
    blocks = find_blocks(content)

    target = None
    for b in blocks:
        if b.block_type == block_type:
            target = b
            break

    block_lines = block_content.splitlines() if block_content else []

    if target is not None:
        # Replace existing block content (keep tags).
        new_lines = [
            *lines[: target.start_line - 1],
            open_tag,
            *block_lines,
            close_tag,
            *lines[target.end_line :],
        ]
    else:
        # Append new block at end of file.
        new_lines = list(lines)
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(open_tag)
        new_lines.extend(block_lines)
        new_lines.append(close_tag)

    result = "\n".join(new_lines)
    if not result.endswith("\n"):
        result += "\n"
    return result


def strip_block(
    content: str,
    block_type: str,
) -> str:
    """Remove a managed block (tags + content) from *content*.

    Returns the content unchanged if no block of *block_type* exists.

    Raises:
        TagError: If the file has malformed tags.
    """
    blocks = find_blocks(content)
    lines = content.splitlines()

    target = None
    for b in blocks:
        if b.block_type == block_type:
            target = b
            break

    if target is None:
        return content

    before = lines[: target.start_line - 1]
    after = lines[target.end_line :]

    # Collapse double blank lines at the seam.
    while before and not before[-1].strip() and after and not after[0].strip():
        before.pop()

    result = "\n".join(before + after)
    if result and not result.endswith("\n"):
        result += "\n"
    if not result.strip():
        return ""
    return result
