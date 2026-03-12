"""Compute lightweight summary statistics for `.vault/` content.

This module aggregates high-level vault counts such as total documents, counts
by `DocType`, and distinct feature totals. It is a summary layer built on
`vaultcore` scanning and verification-derived feature extraction, not a graph
or repair module.

Usage:
    Call `get_vault_metrics(root_dir)` to produce a `VaultSummary` for reports,
    dashboards, or other higher-level tooling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..vaultcore import DocType, get_doc_type, scan_vault

if TYPE_CHECKING:
    import pathlib

logger = logging.getLogger(__name__)

__all__ = ["VaultSummary", "get_vault_metrics"]


@dataclass
class VaultSummary:
    """Aggregate statistics for the vault.

    Attributes:
        total_docs: Total number of documents found in the vault.
        counts_by_type: Document count broken down by DocType category.
        total_features: Number of distinct features referenced across all documents.
    """

    total_docs: int
    counts_by_type: dict[DocType, int]
    total_features: int


def get_vault_metrics(root_dir: pathlib.Path) -> VaultSummary:
    """Calculate summary statistics for the vault.

    Scans all documents under ``root_dir``, tallies them by DocType, and
    counts the number of distinct features present.

    Args:
        root_dir: Root directory of the vault workspace.

    Returns:
        A VaultSummary containing total document count, per-type counts,
        and the number of distinct features.
    """
    logger.info("Collecting vault metrics from %s", root_dir)

    counts = dict.fromkeys(DocType, 0)
    total = 0

    # We'll use a simplified feature extraction here to avoid double-parsing
    # if we just want quick stats. But for robustness we can import list_features.
    from ..verification import list_features

    for path in scan_vault(root_dir):
        total += 1
        doc_type = get_doc_type(path, root_dir)
        if doc_type:
            counts[doc_type] += 1

    feature_count = len(list_features(root_dir))
    logger.info(
        "Metrics collection complete: %d total docs, %d features", total, feature_count
    )
    logger.debug("Counts by type: %s", counts)

    return VaultSummary(
        total_docs=total,
        counts_by_type=counts,
        total_features=feature_count,
    )
