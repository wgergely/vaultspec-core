from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def extract_wiki_links(content: str) -> set[str]:
    """Extracts all [[wiki-links]] from the content."""
    # Matches [[Link Name]] or [[Link Name|Display Name]]
    pattern = r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]"
    matches = re.findall(pattern, content)
    return {m.strip() for m in matches}


def extract_related_links(related: list[str]) -> set[str]:
    """Extracts link targets from the 'related' metadata field."""
    links = set()
    malformed_count = 0
    for link in related:
        # related links are expected to be [[Link Name]]
        match = re.match(r"^\[\[([^\]|]+)(?:\|[^\]]+)?\]\]$", link)
        if match:
            links.add(match.group(1).strip())
        else:
            malformed_count += 1
            logger.debug("Malformed related link: %s", link)
    if malformed_count > 0:
        logger.warning("Found %d malformed links in related field", malformed_count)
    return links
