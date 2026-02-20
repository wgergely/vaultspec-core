from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from vaultcore.models import DocType

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator


def scan_vault(root_dir: pathlib.Path) -> Iterator[pathlib.Path]:
    """Yields all markdown files in the .vault/ directory."""
    from core.config import get_config

    docs_dir = root_dir / get_config().docs_dir
    if not docs_dir.exists():
        logger.debug("Docs directory does not exist: %s", docs_dir)
        return

    file_count = 0
    for path in docs_dir.rglob("*.md"):
        # Skip internal config
        if ".obsidian" in path.parts:
            logger.debug("Skipping .obsidian file: %s", path)
            continue
        file_count += 1
        yield path
    logger.info("Scanned vault: found %d markdown files", file_count)


def get_doc_type(path: pathlib.Path, root_dir: pathlib.Path) -> DocType | None:
    """Determines the DocType based on the file's parent directory."""
    from core.config import get_config

    docs_dir = root_dir / get_config().docs_dir
    try:
        rel_path = path.relative_to(docs_dir)
        if len(rel_path.parts) < 2:
            logger.debug("File has fewer than 2 path parts: %s", rel_path)
            return None
        doc_type = DocType(rel_path.parts[0])
        logger.debug("Determined doc type %s for %s", doc_type, path.name)
        return doc_type
    except (ValueError, KeyError) as e:
        logger.debug("Failed to determine doc type for %s: %s", path.name, e)
        return None
