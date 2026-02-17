"""Root conftest for all vaultspec tests (both lib/tests/ and lib/src/*/tests/).

Discovered by pytest as the common ancestor of both test trees.
The ``pythonpath`` config in pyproject.toml handles sys.path setup;
this file re-exports key constants and provides shared fixtures.
"""

from __future__ import annotations

from tests.constants import PROJECT_ROOT, TEST_PROJECT, TEST_VAULT  # noqa: F401
