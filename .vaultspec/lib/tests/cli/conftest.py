"""Shared fixtures and helpers for CLI sync tests."""

from __future__ import annotations

import argparse
import shutil
from typing import TYPE_CHECKING

import cli
import pytest
from tests.constants import TEST_PROJECT

if TYPE_CHECKING:
    from pathlib import Path


def cleanup_test_project(root: Path) -> None:
    """Remove transient artifacts, preserving .vault/ and README."""
    for item in root.iterdir():
        if item.name in (".vault", "README.md", ".gitignore"):
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


def setup_rules_dir(root: Path) -> None:
    """Create the .vaultspec/ directory structure needed by cli.py."""
    for d in [
        ".vaultspec/rules",
        ".vaultspec/rules/rules",
        ".vaultspec/rules/agents",
        ".vaultspec/rules/skills",
        ".vaultspec/rules/system",
        ".claude/rules",
        ".claude/agents",
        ".claude/skills",
        ".gemini/rules",
        ".gemini/agents",
        ".gemini/skills",
        ".agent/rules",
        ".agent/skills",
    ]:
        (root / d).mkdir(parents=True, exist_ok=True)


def make_ns(**kwargs) -> argparse.Namespace:
    """Build an argparse.Namespace with sensible defaults for sync commands."""
    defaults = {"prune": False, "dry_run": False, "force": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@pytest.fixture(autouse=True)
def _isolate_cli():
    """Reset cli globals to test-project before every test."""
    cli.init_paths(TEST_PROJECT)
    setup_rules_dir(TEST_PROJECT)
    yield
    cleanup_test_project(TEST_PROJECT)
