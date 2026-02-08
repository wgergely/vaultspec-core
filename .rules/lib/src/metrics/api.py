from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from vault.models import DocType
from vault.scanner import get_doc_type, scan_vault

if TYPE_CHECKING:
    import pathlib


@dataclass
class VaultSummary:
    total_docs: int
    counts_by_type: dict[DocType, int]
    total_features: int


def get_vault_metrics(root_dir: pathlib.Path) -> VaultSummary:
    """Calculates summary statistics for the vault."""
    counts = dict.fromkeys(DocType, 0)
    total = 0

    # We'll use a simplified feature extraction here to avoid double-parsing
    # if we just want quick stats. But for robustness we can import list_features.
    from verification.api import list_features

    for path in scan_vault(root_dir):
        total += 1
        doc_type = get_doc_type(path, root_dir)
        if doc_type:
            counts[doc_type] += 1

    return VaultSummary(
        total_docs=total,
        counts_by_type=counts,
        total_features=len(list_features(root_dir)),
    )
