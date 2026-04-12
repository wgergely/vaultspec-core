"""Synthetic vault corpus generator for deterministic testing.

Public API re-exported from the ``synthetic`` module.
"""

from __future__ import annotations

from vaultspec_core.testing.synthetic import (
    PATHOLOGY_NAMES,
    CorpusManifest,
    GeneratedDoc,
    build_multi_project_fixture,
    build_synthetic_vault,
)

__all__ = [
    "PATHOLOGY_NAMES",
    "CorpusManifest",
    "GeneratedDoc",
    "build_multi_project_fixture",
    "build_synthetic_vault",
]
