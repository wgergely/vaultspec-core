from __future__ import annotations

import pathlib
import re
from typing import Dict, Optional, Tuple

from orchestration.types import DocumentMetadata


class SecurityError(Exception):
    """Raised when a path access violates workspace boundaries."""

    pass


def find_project_root() -> pathlib.Path:
    """Walk up from CWD looking for the git repository root.

    Security-critical: uses CWD as the starting point and walks up to find
    the nearest .git directory, which defines the workspace boundary.
    """
    candidate = pathlib.Path.cwd().resolve()
    while candidate != candidate.parent:
        if (candidate / ".git").exists():
            return candidate
        candidate = candidate.parent
    # No .git found — fall back to CWD (non-git usage)
    return pathlib.Path.cwd().resolve()


def safe_read_text(path: pathlib.Path, root_dir: pathlib.Path) -> str:
    """Reads text from a path after verifying it is within the workspace."""
    resolved_path = path.resolve()
    resolved_root = root_dir.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise SecurityError(f"Attempted to access path outside workspace: {path}")

    if not resolved_path.exists():
        return ""
    return resolved_path.read_text(encoding="utf-8")


def parse_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    """Extracts simple key-value pairs from YAML-style frontmatter.

    Legacy support for simple metadata.
    """
    frontmatter: Dict[str, str] = {}
    body = content
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not match:
        return frontmatter, body

    yaml_content = match.group(1)
    body = match.group(2)
    for line in yaml_content.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            frontmatter[key.strip()] = value.strip()
    return frontmatter, body


def parse_vault_metadata(content: str) -> Tuple[DocumentMetadata, str]:
    """Parses rigid vault metadata from markdown content.

    Handles lists (tags, related) and basic fields (date).
    """
    metadata = DocumentMetadata()
    body = content
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
    if not match:
        return metadata, body

    yaml_content = match.group(1)
    body = match.group(2)

    current_key: Optional[str] = None

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
