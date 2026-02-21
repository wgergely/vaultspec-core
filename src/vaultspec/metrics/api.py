from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from vaultspec.vaultcore import DocType, get_doc_type, scan_vault

if TYPE_CHECKING:
    import pathlib

logger = logging.getLogger(__name__)

__all__ = ["VaultSummary", "get_vault_metrics"]


@dataclass
class VaultSummary:
    """Aggregate statistics for the vault."""

    total_docs: int
    counts_by_type: dict[DocType, int]
    total_features: int


def get_vault_metrics(root_dir: pathlib.Path) -> VaultSummary:
    """Calculates summary statistics for the vault."""
    logger.info("Collecting vault metrics from %s", root_dir)

    counts = dict.fromkeys(DocType, 0)
    total = 0

    # We'll use a simplified feature extraction here to avoid double-parsing
    # if we just want quick stats. But for robustness we can import list_features.
    from vaultspec.verification import list_features

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
