"""Shared fixtures and helpers for CLI tests."""

from __future__ import annotations

import os

import pytest
import typer.rich_utils
from typer.testing import CliRunner

from vaultspec_core.cli import app as cli_app
from vaultspec_core.core.types import init_paths

# Disable Rich/Typer color output in tests.  NO_COLOR is the standard
# mechanism (https://no-color.org/) and Rich respects it.  We also force
# Typer's COLOR_SYSTEM to None to prevent ANSI on CI where pseudo-TTY
# detection can override NO_COLOR.
os.environ["NO_COLOR"] = "1"
typer.rich_utils.COLOR_SYSTEM = None


def setup_rules_dir(root):
    """Setup rules source directory in the given root."""
    (root / ".vaultspec" / "rules" / "rules").mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="session")
def runner():
    return CliRunner(env={"NO_COLOR": "1"})


@pytest.fixture
def test_project(tmp_path):
    """Provide an isolated test project directory with full structure."""
    project = tmp_path / "project"
    project.mkdir()

    # Create .vaultspec structure
    (project / ".vaultspec" / "rules" / "rules").mkdir(parents=True)
    (project / ".vaultspec" / "rules" / "skills").mkdir(parents=True)
    (project / ".vaultspec" / "rules" / "templates").mkdir(parents=True)
    (project / ".vaultspec" / "rules" / "system").mkdir(parents=True)

    # Create .vault structure
    for subdir in ["adr", "audit", "exec", "plan", "reference", "research"]:
        (project / ".vault" / subdir).mkdir(parents=True)

    # Create tool directories (needed for sync tests)
    (project / ".claude" / "rules").mkdir(parents=True)
    (project / ".claude" / "skills").mkdir(parents=True)
    (project / ".gemini" / "rules").mkdir(parents=True)

    # Mock init_paths to point to this temp project
    from vaultspec_core.config.workspace import resolve_workspace

    layout = resolve_workspace(target_override=project)
    init_paths(layout)

    return project


def run_vaultspec(runner, *args, target=None):
    args_list = list(args)
    if target and "--target" not in args_list and "-t" not in args_list:
        args_list = ["--target", str(target), *args_list]
    return runner.invoke(cli_app, args_list)


def run_vault(runner, *args, target=None):
    args_list = list(args)
    if target and "--target" not in args_list and "-t" not in args_list:
        args_list = ["--target", str(target), *args_list]

    # Ensure 'vault' is in args_list
    if "vault" not in args_list:
        # Insert 'vault' after global options if any
        inserted = False
        for i in range(len(args_list)):
            if args_list[i] in ("--target", "-t"):
                args_list.insert(i + 2, "vault")
                inserted = True
                break
        if not inserted:
            args_list.insert(0, "vault")

    return runner.invoke(cli_app, args_list)


def run_spec(runner, *args, target=None):
    args_list = list(args)
    if target and "--target" not in args_list and "-t" not in args_list:
        args_list = ["--target", str(target), *args_list]
    return runner.invoke(cli_app, args_list)


@pytest.fixture(autouse=True)
def _isolate_cli(test_project):
    """Ensure every test has its own isolated project state and console."""
    from vaultspec_core.console import reset_console

    reset_console()
    yield
    reset_console()
