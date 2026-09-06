"""Parse frontmatter and normalize vault metadata into typed models.

This module provides both generic YAML frontmatter extraction and stricter
vault-specific parsing that converts markdown metadata into validated domain
objects. It favors tolerant text handling at the input boundary while
producing a rigid output model.

Usage:
    Use `parse_frontmatter(...)` for low-level extraction and
    `parse_vault_metadata(...)` when the caller needs validated vault metadata.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

from .models import DocumentMetadata

__all__ = ["SafeLoader", "parse_frontmatter", "parse_vault_metadata"]

logger = logging.getLogger(__name__)


def _simple_yaml_load(text: str) -> dict[str, Any]:
    """Minimal key-value YAML parser for simple frontmatter.

    Handles ``key: value`` pairs, preserving colons in values.
    Does NOT handle nested structures, multi-line values, or lists.

    Args:
        text: Raw YAML text (without ``---`` delimiters).

    Returns:
        Dictionary of parsed key-value pairs.
    """
    data: dict[str, Any] = {}
    for line in text.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


_yaml_load: Callable[[str], dict[str, Any]]

try:
    import yaml

    try:
        # Prefer the libyaml-backed C loader: it parses frontmatter several
        # times faster than the pure-Python SafeLoader with identical safe
        # semantics. Every vault scan, graph build, check, and MCP tool call
        # parses frontmatter, so this is the hottest parse path in the system.
        # Both branches bind the name ``SafeLoader`` unaliased: each derives
        # from ``yaml.constructor.SafeConstructor``, which is what refuses the
        # ``!!python/object`` tags that would otherwise instantiate arbitrary
        # objects out of document frontmatter.
        from yaml import CSafeLoader as SafeLoader
    except ImportError:  # pragma: no cover - PyYAML built without libyaml
        from yaml import SafeLoader

    def _yaml_load_impl(text: str) -> dict[str, Any]:
        """Load YAML text via PyYAML, falling back to the simple parser on error.

        A YAML document is not necessarily a mapping (a sequence or a bare
        scalar are both legal YAML). Every caller of this function treats its
        result as a ``dict`` without checking, so a non-mapping result is
        coerced to ``{}`` here at the parser boundary rather than raising:
        this is the same "malformed document degrades to empty metadata"
        model ``parse_vault_metadata``'s hand-written scanner already applies
        (a sequence frontmatter block simply matches none of its known
        ``key:`` patterns), and it lets the existing ``vault check
        frontmatter`` diagnostics - which already report missing tags/date as
        check violations - catch the malformed document downstream instead
        of a crash pre-empting every command that builds the graph.

        Args:
            text: Raw YAML text (without ``---`` delimiters).

        Returns:
            Dictionary of parsed key-value pairs; ``{}`` when the document
            parses to ``None`` or to a non-mapping value.
        """
        try:
            loaded = yaml.load(text, Loader=SafeLoader)
        except yaml.YAMLError as e:
            # PyYAML chokes on unquoted colons in values (e.g.
            # ``description: A test: with colons``).  Fall back to
            # the simple key-value splitter which handles them fine.
            #
            # Log only a summary line, not the full frontmatter block: this
            # warning is the kind of thing that ends up pasted verbatim into
            # a public bug report, and the block itself may carry sensitive
            # values the author never intended to publish.
            logger.warning(
                "PyYAML parse error on %d-char frontmatter block (starts %r): "
                "%s; falling back to simple parser",
                len(text),
                text.strip().splitlines()[0][:80] if text.strip() else "",
                e,
            )
            return _simple_yaml_load(text)
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            logger.warning(
                "Frontmatter parsed to a %s, not a mapping (starts %r); "
                "treating as empty metadata",
                type(loaded).__name__,
                text.strip().splitlines()[0][:80] if text.strip() else "",
            )
            return {}
        return cast("dict[str, Any]", loaded)

    _yaml_load = _yaml_load_impl

except ImportError:
    _yaml_load = _simple_yaml_load


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter and return (metadata dict, body).

    Uses PyYAML when available, falling back to a simple key-value
    splitter otherwise.

    Args:
        content: Raw markdown text, optionally beginning with ``---`` fenced
            YAML frontmatter.

    Returns:
        A two-tuple of ``(frontmatter_dict, body)`` where ``body`` is the
        markdown content after the closing ``---`` fence, or the full content
        if no frontmatter is present.
    """
    # A UTF-8 BOM (U+FEFF) is not whitespace, so ``str.lstrip`` leaves it in
    # place and the ``---`` fence check below would fail - silently classifying
    # a perfectly valid BOM-prefixed document as having no frontmatter. Strip a
    # single leading BOM first so BOM docs are discovered everywhere this parser
    # runs (vault scan, feature listing, graph build, every check).
    if content.startswith("\ufeff"):
        content = content[1:]
    content = content.lstrip()
    frontmatter: dict[str, Any] = {}
    body = content
    if not content.startswith("---"):
        return frontmatter, body
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
    if not match:
        return frontmatter, body

    try:
        frontmatter = _yaml_load(match.group(1))
    except Exception as e:
        # Summarize rather than dump the block: this is the kind of warning
        # that gets pasted verbatim into a public bug report, and the block
        # itself may carry values the author never intended to publish.
        yaml_block = match.group(1)
        logger.warning(
            "Failed to parse %d-char frontmatter block (starts %r): %s",
            len(yaml_block),
            yaml_block.strip().splitlines()[0][:80] if yaml_block.strip() else "",
            e,
            exc_info=True,
        )
        frontmatter = {}
    body = match.group(2)
    return frontmatter, body


def parse_vault_metadata(content: str) -> tuple[DocumentMetadata, str]:
    """Parse rigid vault metadata from the YAML frontmatter of a markdown document.

    Uses a hand-written line scanner that tolerates the YAML list syntax
    used by the vault schema (``- "value"`` items under ``tags:`` /
    ``related:``).

    Date-shaped fields are stored as authored so the check/fix pass can see
    and repair a non-canonical stamp; the parsed reading is
    :attr:`~vaultspec_core.vaultcore.models.DocumentMetadata.parsed_date`,
    which is what a consumer acting on the value - rather than reporting it
    - is expected to read.

    Args:
        content: Raw markdown text, optionally beginning with ``---`` fenced
            YAML frontmatter.

    Returns:
        A two-tuple of ``(DocumentMetadata, body)`` where ``body`` is the
        markdown content that follows the closing ``---`` fence, or the full
        content if no frontmatter is present.
    """
    # Strip a single leading UTF-8 BOM (U+FEFF) before whitespace: it is not
    # whitespace, so ``str.lstrip`` would leave it in front of the ``---`` fence
    # and the document would parse as having no metadata - silently dropping its
    # tags and making it invisible to every feature scan and check.
    if content.startswith("\ufeff"):
        content = content[1:]
    content = content.lstrip()
    metadata = DocumentMetadata()
    body = content
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
    if not match:
        return metadata, body

    yaml_content = match.group(1)
    body = match.group(2)

    current_key: str | None = None

    for line in yaml_content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if ":" in line and not line.startswith("-"):
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            current_key = key

            if key == "date":
                # Retained as authored: `vault check all --fix` normalizes
                # non-canonical stamps and can only do so while it can still
                # see what was written. The typed reading lives on
                # `DocumentMetadata.parsed_date`, and every consumer that
                # would let this value decide a path reads it there - the
                # raw string is text for reporting and repair, never a path
                # segment.
                metadata.date = val.strip("\"'")
            elif key == "modified":
                metadata.modified = val.strip("\"'") or None
            elif key == "superseded_by":
                metadata.superseded_by = val.strip("\"'") or None
            elif key == "archived":
                metadata.archived = val.strip("\"'") or None
            elif key == "step_id":
                metadata.step_id = val.strip("\"'") or None
            elif key == "body_schema":
                metadata.body_schema = val.strip("\"'") or None
            elif key == "body_hash":
                metadata.body_hash = val.strip("\"'") or None
            elif val.startswith("[") and val.endswith("]"):
                # Simple inline list parsing: ["#a", "#b"]
                items = [
                    i.strip().strip("\"'") for i in val[1:-1].split(",") if i.strip()
                ]
                if key == "tags":
                    metadata.tags = items
                elif key == "related":
                    metadata.related = items
                elif key == "supersedes":
                    metadata.supersedes = items
                elif key == "derived_from":
                    metadata.derived_from = items
                elif key == "promoted_to":
                    metadata.promoted_to = items
        elif line.startswith("-") and current_key:
            # Bulleted list item
            val = line[1:].strip().strip("\"'")
            if current_key == "tags":
                metadata.tags.append(val)
            elif current_key == "related":
                metadata.related.append(val)
            elif current_key == "supersedes":
                metadata.supersedes.append(val)
            elif current_key == "derived_from":
                metadata.derived_from.append(val)
            elif current_key == "promoted_to":
                metadata.promoted_to.append(val)

    return metadata, body
