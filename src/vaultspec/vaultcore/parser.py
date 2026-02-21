from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from .models import DocumentMetadata

__all__ = ["parse_frontmatter", "parse_vault_metadata"]

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


def _simple_yaml_load(text: str) -> dict[str, Any]:
    """Minimal key-value YAML parser for simple frontmatter.

    Handles ``key: value`` pairs, preserving colons in values.
    Does NOT handle nested structures, multi-line values, or lists.
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

    def _yaml_load_impl(text: str) -> dict[str, Any]:
        try:
            return yaml.safe_load(text) or {}
        except yaml.YAMLError:
            # PyYAML chokes on unquoted colons in values (e.g.
            # ``description: A test: with colons``).  Fall back to
            # the simple key-value splitter which handles them fine.
            return _simple_yaml_load(text)

    _yaml_load = _yaml_load_impl

except ImportError:
    _yaml_load = _simple_yaml_load


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter and return (metadata dict, body).

    Uses PyYAML when available, falling back to a simple key-value
    splitter otherwise.
    """
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
        logger.warning("Failed to parse frontmatter: %s", e)
        frontmatter = {}
    body = match.group(2)
    return frontmatter, body


def parse_vault_metadata(content: str) -> tuple[DocumentMetadata, str]:
    """Parses rigid vault metadata from markdown content."""
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
                metadata.date = val.strip("\"'")
            elif val.startswith("[") and val.endswith("]"):
                # Simple inline list parsing: ["#a", "#b"]
                items = [
                    i.strip().strip("\"'") for i in val[1:-1].split(",") if i.strip()
                ]
                if key == "tags":
                    metadata.tags = items
                elif key == "related":
                    metadata.related = items
        elif line.startswith("-") and current_key:
            # Bulleted list item
            val = line[1:].strip().strip("\"'")
            if current_key == "tags":
                metadata.tags.append(val)
            elif current_key == "related":
                metadata.related.append(val)

    return metadata, body
