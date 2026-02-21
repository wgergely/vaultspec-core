"""Root conftest for all vaultspec tests (both tests/ and src/vaultspec/*/tests/).

Discovered by pytest as the common ancestor of both test trees.
Re-exports key constants and provides shared fixtures.
"""

from __future__ import annotations

from tests.constants import PROJECT_ROOT, TEST_PROJECT, TEST_VAULT  # noqa: F401
