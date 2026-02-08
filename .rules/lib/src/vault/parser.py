from __future__ import annotations

import re

from vault.models import DocumentMetadata


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Extracts simple key-value pairs from YAML-style frontmatter."""
    frontmatter: dict[str, str] = {}
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


def parse_vault_metadata(content: str) -> tuple[DocumentMetadata, str]:
    """Parses rigid vault metadata from markdown content."""
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
