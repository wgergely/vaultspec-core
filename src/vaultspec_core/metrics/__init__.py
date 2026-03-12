"""Expose the vault summary-metrics package facade.

This package re-exports the `api` surface that computes lightweight aggregate
statistics over `.vault/` content.
"""

from .api import VaultSummary as VaultSummary
from .api import get_vault_metrics as get_vault_metrics
