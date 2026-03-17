"""Extract wiki-link relationships from vault documents.

This module provides focused helpers for reading internal links from markdown
bodies and `related:` frontmatter fields. It exists to keep vault link parsing
narrow, reusable, and separate from broader metadata parsing.
"""

from __future__ import annotations

import logging
import re

__all__ = ["extract_related_links", "extract_wiki_links"]

logger = logging.getLogger(__name__)


def extract_wiki_links(content: str) -> set[str]:
    """Extract all ``[[wiki-link]]`` targets from a markdown string.

    Handles both ``[[Target]]`` and ``[[Target|Display]]`` forms; only the
    target (left-hand) portion is returned.

    Args:
        content: Raw markdown text to scan.

    Returns:
        Set of unique link target strings with surrounding whitespace stripped.
    """
    # Matches [[Link Name]] or [[Link Name|Display Name]]
    pattern = r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]"
    matches = re.findall(pattern, content)
    targets = set()
    for m in matches:
        target = m.strip()
        # Tolerate .md extensions (Obsidian convention: [[note-name]] without extension)
        if target.endswith(".md"):
            target = target[:-3]
        targets.add(target)
    return targets


def extract_related_links(related: list[str]) -> set[str]:
    """Extract link targets from the ``related`` YAML frontmatter field.

    Each entry is expected to be a ``[[wiki-link]]`` string.  Malformed
    entries are logged and skipped.

    Args:
        related: List of raw ``related`` values from parsed frontmatter.

    Returns:
        Set of resolved link target strings.
    """
    links = set()
    malformed_count = 0
    for link in related:
        # related links are expected to be [[Link Name]]
        match = re.match(r"^\[\[([^\]|]+)(?:\|[^\]]+)?\]\]$", link)
        if match:
            target = match.group(1).strip()
            # Strip .md (Obsidian wiki-link convention)
            if target.endswith(".md"):
                target = target[:-3]
            links.add(target)
        else:
            malformed_count += 1
            logger.debug("Malformed related link: %s", link)
    if malformed_count > 0:
        logger.warning("Found %d malformed links in related field", malformed_count)
    return links
