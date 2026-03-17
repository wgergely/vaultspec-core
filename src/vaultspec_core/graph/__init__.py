"""Expose the graph-analysis package facade.

This package re-exports the `api` surface that builds and queries vault
document relationship graphs from `.vault/` content.
"""

from .api import DocNode as DocNode
from .api import GraphMetrics as GraphMetrics
from .api import VaultGraph as VaultGraph
