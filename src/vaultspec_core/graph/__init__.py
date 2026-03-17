"""Vault document relationship graph backed by ``networkx.DiGraph``.

Scans ``.vault/`` content, resolves wiki-links and ``related:`` fields into
directed edges, and exposes query, render (ASCII via ``phart``, Rich tree), and
JSON-serialisation (``networkx`` node-link format) operations.

Exports:
    :class:`VaultGraph`: Main entry point; instantiate with a vault root.
    :class:`DocNode`: Per-document node carrying frontmatter, body, and link metadata.
    :class:`GraphMetrics`: Aggregate statistics computed by ``networkx`` algorithms.
"""

from .api import DocNode as DocNode
from .api import GraphMetrics as GraphMetrics
from .api import VaultGraph as VaultGraph
