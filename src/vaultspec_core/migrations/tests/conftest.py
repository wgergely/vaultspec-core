"""Shared fixtures for migration tests.

Mirrors the CLI suite's autouse workspace-context isolation: migration tests
that provision real workspaces bind the global workspace context via
``init_paths``, and without a save/restore boundary that context leaks into
whichever test collects next (the no-context collector tests are the first
casualties under full-gate ordering).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import vaultspec_core.core.types as _t
from vaultspec_core.core.manifest import ManifestData, write_manifest_data
from vaultspec_core.migrations import reset_workspace_cache

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def isolate_state():
    """Save and restore workspace context, target, config, and console."""
    from vaultspec_core.cli._target import reset as reset_target
    from vaultspec_core.config import reset_config
    from vaultspec_core.console import reset_console
    from vaultspec_core.core.types import get_context, set_context

    try:
        current = get_context()
    except LookupError:
        _sentinel = Path(".")
        current = _t.WorkspaceContext(
            root_dir=_sentinel,
            target_dir=_sentinel,
            rules_src_dir=_sentinel,
            skills_src_dir=_sentinel,
            agents_src_dir=_sentinel,
            system_src_dir=_sentinel,
            templates_dir=_sentinel,
            hooks_dir=_sentinel,
        )

    set_context(current)

    reset_console()
    reset_target()
    reset_config()

    yield

    set_context(current)
    reset_console()
    reset_target()
    reset_config()


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    """Create an installed-style workspace with a writable manifest.

    Writes a stale ``vaultspec_version`` so the driver has something
    to migrate. Resets the per-process workspace cache so each test
    starts from a clean slate.

    Returns:
        The workspace root path. Tests still hit a real on-disk
        manifest and a real workspace path; no library functions are
        mocked.
    """
    fw_dir = tmp_path / ".vaultspec"
    fw_dir.mkdir(parents=True, exist_ok=True)
    data = ManifestData(vaultspec_version="0.1.0")
    write_manifest_data(tmp_path, data)
    reset_workspace_cache()
    yield tmp_path
    reset_workspace_cache()
