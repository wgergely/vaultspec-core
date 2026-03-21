"""Aggregate vault statistics surface for vaultspec-core.

Re-exports :class:`~vaultspec_core.metrics.api.VaultSummary` and
:func:`~vaultspec_core.metrics.api.get_vault_metrics` from :mod:`.api`.
Consumes :mod:`vaultspec_core.vaultcore` scanning and query primitives
to compute document counts and feature totals over ``.vault/`` content.
"""

from .api import VaultSummary as VaultSummary
from .api import get_vault_metrics as get_vault_metrics
