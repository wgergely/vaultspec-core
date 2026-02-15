"""Shared fixtures and helpers for CLI sync tests."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import cli
import pytest

TEST_PROJECT = Path(__file__).resolve().parent.parent.parent.parent / "test-project"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        ".vaultspec/rules-custom",
        ".vaultspec/agents",
        ".vaultspec/skills",
        ".vaultspec/system",
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


# Patch PROVIDERS so tests never depend on actual model resolution
MOCK_PROVIDERS: dict[str, dict[str, str]] = {
    "claude": {"LOW": "claude-haiku", "MEDIUM": "claude-sonnet", "HIGH": "claude-opus"},
    "gemini": {"LOW": "gemini-flash", "MEDIUM": "gemini-pro", "HIGH": "gemini-ultra"},
}


def mock_resolve_model(tool: str, tier: str) -> str | None:
    provider = MOCK_PROVIDERS.get(tool)
    if provider is None:
        return None
    return provider.get(tier.upper())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_cli():
    """Reset cli globals to test-project before every test."""
    cli.init_paths(TEST_PROJECT)
    setup_rules_dir(TEST_PROJECT)
    yield
    cleanup_test_project(TEST_PROJECT)
