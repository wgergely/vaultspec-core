"""Versioned migration for vaultspec-core 0.1.21.

Introducing frontmatter lifecycle fields.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import Migration, MigrationResult, MigrationScope

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["MIGRATION", "migrate"]

logger = logging.getLogger(__name__)

_TARGET_VERSION = "0.1.21"
_NAME = "frontmatter_lifecycle"


def migrate(workspace: Path) -> MigrationResult:
    """Additive migration for frontmatter lifecycle fields.

    Existing files do not require rewriting as the fields are optional.

    Args:
        workspace: Workspace root directory.

    Returns:
        MigrationResult indicating success.
    """
    logger.debug("Running migration %s in %s", _NAME, workspace)
    return MigrationResult(
        name=_NAME,
        target_version=_TARGET_VERSION,
        summary="additive schema migration for frontmatter lifecycle fields (no-op)",
        counts={},
    )


MIGRATION = Migration(
    target_version=_TARGET_VERSION,
    name=_NAME,
    migrate=migrate,
    # Rewrites the frontmatter of documents a human authored.
    scope=MigrationScope.DOCUMENT_CONTENT,
)
