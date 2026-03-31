"""Discover vault documents on disk and classify them by document type.

This module bridges the filesystem and the vault domain model by locating
markdown files, inferring their document kind, and preparing them for parsing
and downstream analysis.

Usage:
    Use `scan_vault(root_dir)` to iterate the document set and
    `get_doc_type(...)` when a caller needs type classification for an
    individual file.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .models import DocType

__all__ = ["get_doc_type", "list_features", "scan_vault"]

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator


def scan_vault(root_dir: pathlib.Path) -> Iterator[pathlib.Path]:
    """Yield all markdown files under the configured docs directory.

    Skips hidden ``.obsidian`` subtrees.

    Args:
        root_dir: Project root that contains the docs directory.

    Yields:
        Absolute paths to each ``.md`` file found.
    """
    from ..config import get_config

    docs_dir = root_dir / get_config().docs_dir
    if not docs_dir.exists():
        logger.debug("Docs directory does not exist: %s", docs_dir)
        return

    file_count = 0
    for path in docs_dir.rglob("*.md"):
        # Skip internal config and archived documents
        if ".obsidian" in path.parts or "_archive" in path.parts:
            logger.debug("Skipping excluded path: %s", path)
            continue
        file_count += 1
        yield path
    logger.info("Scanned vault: found %d markdown files", file_count)


def list_features(root_dir: pathlib.Path) -> set[str]:
    """Infer the set of feature names from tags across all vault documents.

    Args:
        root_dir: Project root containing the docs directory.

    Returns:
        Set of feature name strings (without the leading ``#``).
    """
    from .parser import parse_vault_metadata

    logger.debug("Extracting features from vault")
    features: set[str] = set()
    skip_count = 0
    for path in scan_vault(root_dir):
        try:
            content = path.read_text(encoding="utf-8")
            metadata, _ = parse_vault_metadata(content)
            for tag in metadata.tags:
                if not DocType.from_tag(tag):
                    features.add(tag.lstrip("#"))
        except (OSError, UnicodeDecodeError):
            skip_count += 1
            logger.warning("Failed to read feature tags from %s", path.name)
            continue
    logger.info(
        "Feature extraction complete: found %d features, skipped %d files",
        len(features),
        skip_count,
    )
    return features


def get_doc_type(path: pathlib.Path, root_dir: pathlib.Path) -> DocType | None:
    """Determine the DocType of a vault file based on its parent directory.

    Args:
        path: Absolute path to the vault document.
        root_dir: Project root used to resolve the docs directory prefix.

    Returns:
        The ``DocType`` inferred from the first path component relative to the
        docs directory, or ``None`` if the path does not match any known type.
    """
    from ..config import get_config

    docs_dir = root_dir / get_config().docs_dir
    try:
        rel_path = path.relative_to(docs_dir)
        if len(rel_path.parts) < 2:
            # Root-level files: check for feature index pattern
            if path.name.endswith(".index.md"):
                return DocType.INDEX
            logger.debug("File has fewer than 2 path parts: %s", rel_path)
            return None
        doc_type = DocType(rel_path.parts[0])
        logger.debug("Determined doc type %s for %s", doc_type, path.name)
        return doc_type
    except (ValueError, KeyError) as e:
        logger.debug("Failed to determine doc type for %s: %s", path.name, e)
        return None
