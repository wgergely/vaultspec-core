"""Shared fixtures for the CLI test suite.

Provides the session-scoped ``runner``, the ``test_project`` workspace
fixture backed by the real ``test-project/`` corpus, and autouse isolation
that saves/restores module-level globals between tests.  Color output is
disabled globally via ``NO_COLOR=1``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import typer.rich_utils
from typer.testing import CliRunner

import vaultspec_core.core.types as _t
from vaultspec_core.cli import app
from vaultspec_core.config.workspace import resolve_workspace
from vaultspec_core.core.types import init_paths

# Disable Rich/Typer color output in tests.
os.environ["NO_COLOR"] = "1"
typer.rich_utils.COLOR_SYSTEM = None

# Path to the real test-project/ corpus at the repository root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_TEST_PROJECT_SRC = _REPO_ROOT / "test-project"

# Names of the module-level globals that init_paths() sets.
_TYPES_GLOBALS = [
    "ROOT_DIR",
    "TARGET_DIR",
    "RULES_SRC_DIR",
    "SKILLS_SRC_DIR",
    "AGENTS_SRC_DIR",
    "SYSTEM_SRC_DIR",
    "TEMPLATES_DIR",
    "HOOKS_DIR",
    "TOOL_CONFIGS",
]


def setup_rules_dir(root):
    """Setup rules source directory in the given root."""
    (root / ".vaultspec" / "rules" / "rules").mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="session")
def runner():
    return CliRunner(env={"NO_COLOR": "1"})


@pytest.fixture
def test_project(tmp_path):
    """Copy the real test-project/ corpus and install vaultspec.

    Each test gets a fresh copy of the full test-project/ tree including
    .vault/ documentation.  ``install_run`` is called to scaffold
    ``.vaultspec/`` and provider destinations so that all commands work.
    The original test-project/ is never modified.  Cleanup is automatic
    via pytest's ``tmp_path``.

    Module globals are initialised via ``init_paths`` so that unit tests
    calling internal functions (``collect_rules``, ``rules_sync``, etc.)
    have the paths they rely on.
    """
    dest = tmp_path / "project"
    shutil.copytree(
        _TEST_PROJECT_SRC,
        dest,
        ignore_dangling_symlinks=True,
        ignore=shutil.ignore_patterns("*.log"),
    )

    # Install vaultspec framework so .vaultspec/ exists
    from vaultspec_core.core.commands import install_run

    _t.TARGET_DIR = dest
    install_run(path=dest, provider="all", upgrade=False, dry_run=False, force=False)

    layout = resolve_workspace(target_override=dest)
    init_paths(layout)

    return dest


def run_vaultspec(runner, *args, target=None):
    """Invoke the CLI with optional --target."""
    args_list = list(args)
    if target and "--target" not in args_list and "-t" not in args_list:
        args_list = [*args_list, "--target", str(target)]
    return runner.invoke(app, args_list)


def run_vault(runner, *args, target=None):
    """Invoke the CLI with ``vault`` prefix and optional --target."""
    args_list = list(args)
    if target and "--target" not in args_list and "-t" not in args_list:
        args_list = [*args_list, "--target", str(target)]
    if "vault" not in args_list:
        args_list.insert(0, "vault")
    return runner.invoke(app, args_list)


def run_spec(runner, *args, target=None):
    """Invoke the CLI with optional --target (spec commands)."""
    args_list = list(args)
    if target and "--target" not in args_list and "-t" not in args_list:
        args_list = [*args_list, "--target", str(target)]
    return runner.invoke(app, args_list)


@pytest.fixture(autouse=True)
def _isolate_state():
    """Save and restore module-level globals and console between tests.

    This prevents state leakage when one test's CLI invocation sets
    ``_t.TARGET_DIR`` / ``_t.TOOL_CONFIGS`` and the next test inherits
    stale values pointing at the wrong tmp_path.
    """
    from vaultspec_core.cli._target import reset as reset_target
    from vaultspec_core.console import reset_console

    # Snapshot current state.
    saved = {name: getattr(_t, name) for name in _TYPES_GLOBALS}
    reset_console()
    reset_target()

    yield

    # Restore original state.
    for name, value in saved.items():
        setattr(_t, name, value)
    reset_console()
    reset_target()
