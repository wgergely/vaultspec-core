from __future__ import annotations

import re


def extract_wiki_links(content: str) -> set[str]:
    """Extracts all [[wiki-links]] from the content."""
    # Matches [[Link Name]] or [[Link Name|Display Name]]
    pattern = r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]"
    matches = re.findall(pattern, content)
    return {m.strip() for m in matches}


def extract_related_links(related: list[str]) -> set[str]:
    """Extracts link targets from the 'related' metadata field."""
    links = set()
    for link in related:
        # related links are expected to be [[Link Name]]
        match = re.match(r"^\[\[([^\]|]+)(?:\|[^\]]+)?\]\]$", link)
        if match:
            links.add(match.group(1).strip())
    return links
