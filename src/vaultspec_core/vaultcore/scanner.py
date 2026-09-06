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

from .exclusions import is_excluded_vault_path
from .models import DocType

__all__ = [
    "get_doc_type",
    "get_doc_type_from_tree_path",
    "list_features",
    "scan_vault",
]

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator


def scan_vault(root_dir: pathlib.Path) -> Iterator[pathlib.Path]:
    """Yield all markdown files under the configured docs directory.

    Skips the non-corpus subtrees named by
    :data:`~vaultspec_core.vaultcore.exclusions.EXCLUDED_VAULT_DIR_NAMES` -
    editor state, archived documents, and the pre-deletion snapshots under
    ``.trash/``. Reports the corpus exactly as it is on disk: the scan never
    converges the workspace schema.

    This function used to run the migration registry before walking the
    tree, on the reasoning that every vault command should observe a
    post-migration layout. That put a workspace-wide rewrite behind the
    single call every read shares. A read-only MCP ``find`` consequently
    ran the ``exec_ledger_only`` migration and deleted 47 tracked
    documents from a clean worktree (issue #443). Convergence is a
    mutation and now belongs only to callers that asked for one:
    ``install --upgrade``, ``vaultspec-core migrations run``,
    ``vault repair``, and the two layout-sensitive authoring verbs behind
    :func:`vaultspec_core.cli._migration_hook.ensure_migrated`. The scan
    only *reports* the drift, via
    :func:`vaultspec_core.migrations.warn_if_pending`, once per workspace
    per process.

    Args:
        root_dir: Project root that contains the docs directory.

    Yields:
        Absolute paths to each ``.md`` file found.
    """
    from ..config import get_config
    from ..migrations import warn_if_pending

    warn_if_pending(root_dir)

    docs_dir = root_dir / get_config().docs_dir
    if not docs_dir.exists():
        logger.debug("Docs directory does not exist: %s", docs_dir)
        return

    file_count = 0
    for path in docs_dir.rglob("*.md"):
        # Skip internal config and archived documents
        if is_excluded_vault_path(path):
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
    """Determine the :class:`DocType` of a vault file from its parent directory.

    Index files are recognised in two ways. The canonical case is a file
    inside the configured index subdirectory (``docs_dir/index_dir/``).
    The legacy case is a root-level ``<feature>.index.md`` file at
    ``docs_dir/`` itself; this is preserved as a backwards-compatible
    classification path so vaults that have not yet run the migration
    still report sensibly.

    Args:
        path: Absolute path to the vault document.
        root_dir: Project root used to resolve the docs directory prefix.

    Returns:
        The :class:`DocType` inferred from the first path component
        relative to the docs directory, or ``None`` if the path does not
        match any known type.
    """
    from ..config import get_config

    cfg = get_config()
    docs_dir = root_dir / cfg.docs_dir
    try:
        rel_path = path.relative_to(docs_dir)
        if len(rel_path.parts) < 2:
            # Root-level legacy index files are still recognised so that
            # unmigrated vaults classify them correctly until the
            # schema migration registry relocates them (lazily on the
            # next vault command, or explicitly via
            # ``vaultspec-core migrations run``).
            if path.name.endswith(".index.md"):
                logger.debug("Legacy root-level index file detected: %s", path.name)
                return DocType.INDEX
            logger.debug("File has fewer than 2 path parts: %s", rel_path)
            return None
        # ``DocType("index")`` resolves to :attr:`DocType.INDEX`, so the
        # canonical ``index/`` subfolder is classified by the same enum
        # lookup that handles every other typed subdirectory; no special
        # case is required here.
        doc_type = DocType(rel_path.parts[0])
        logger.debug("Determined doc type %s for %s", doc_type, path.name)
        return doc_type
    except (ValueError, KeyError) as e:
        logger.debug("Failed to determine doc type for %s: %s", path.name, e)
        return None


def get_doc_type_from_tree_path(tree_path: str, docs_dir_name: str) -> DocType | None:
    """Classify a vault document from a git tree-path string.

    The ref-scoped graph build (issue #160) reads documents from the git
    object database, where each blob is known by its repo-relative POSIX
    tree path (e.g. ``.vault/adr/foo.md``) rather than a filesystem
    :class:`~pathlib.Path`. This reproduces :func:`get_doc_type`'s
    classification - the first path component after the docs directory names
    the type, with the legacy root-level ``<feature>.index.md`` case
    preserved - from that string alone, so a ref build classifies documents
    identically to a working-tree build without a checkout.

    Args:
        tree_path: Repo-relative POSIX path of the document
            (e.g. ``.vault/adr/foo.md``).
        docs_dir_name: The configured docs directory name (e.g. ``.vault``).

    Returns:
        The :class:`DocType` inferred from the first component after the docs
        directory, or ``None`` when the path does not match a known type.
    """
    from pathlib import PurePosixPath

    parts = PurePosixPath(tree_path).parts
    if docs_dir_name not in parts:
        return None
    rest = parts[parts.index(docs_dir_name) + 1 :]
    if len(rest) < 2:
        if rest and rest[-1].endswith(".index.md"):
            return DocType.INDEX
        return None
    try:
        return DocType(rest[0])
    except (ValueError, KeyError):
        return None
