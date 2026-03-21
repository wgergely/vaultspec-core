"""Tests for manifest-aware sync filtering.

Covers :func:`~vaultspec_core.core.sync.sync_to_all_tools` behaviour when a
provider manifest is present or absent, verifying that only installed providers
receive synced files.
"""

from pathlib import Path

import pytest

from vaultspec_core.core import types as _t
from vaultspec_core.core.enums import Tool
from vaultspec_core.core.manifest import write_manifest
from vaultspec_core.core.sync import sync_to_all_tools

pytestmark = [pytest.mark.unit]


@pytest.fixture
def sync_workspace(tmp_path):
    """Set up a minimal workspace with .vaultspec for sync testing."""
    # Save and restore TARGET_DIR
    old_target = _t.TARGET_DIR
    _t.TARGET_DIR = tmp_path

    # Create minimal vaultspec directory
    vaultspec = tmp_path / ".vaultspec"
    vaultspec.mkdir()

    # Create tool destination dirs in TOOL_CONFIGS temporarily
    old_configs = dict(_t.TOOL_CONFIGS)

    # Set up real tool config dirs pointing to tmp_path
    from vaultspec_core.core.types import ToolConfig

    _t.TOOL_CONFIGS = {}
    for tool in Tool:
        rules_dir = tmp_path / f".{tool.value}" / "rules"
        _t.TOOL_CONFIGS[tool] = ToolConfig(
            name=tool.value,
            rules_dir=rules_dir,
            skills_dir=tmp_path / f".{tool.value}" / "skills",
            agents_dir=tmp_path / f".{tool.value}" / "agents",
            config_file=None,
        )

    yield tmp_path

    _t.TARGET_DIR = old_target
    _t.TOOL_CONFIGS = old_configs


def _noop_transform(_tool, name, meta, body):
    return body


def _default_dest_path(dest_dir, name):
    return dest_dir / name


class TestManifestAwareSync:
    """Verify that sync targets respect the provider manifest."""

    def test_sync_respects_manifest(self, sync_workspace):
        """When manifest exists with only claude, only claude gets synced."""
        write_manifest(sync_workspace, {"claude"})

        sources: dict[str, tuple[Path, dict, str]] = {
            "test.md": (Path(), {}, "Test content.\n"),
        }
        sync_to_all_tools(sources, "rules_dir", _noop_transform, "Rules")

        # Claude should have the file
        assert (sync_workspace / ".claude" / "rules" / "test.md").exists()
        # Others should NOT
        assert not (sync_workspace / ".gemini" / "rules" / "test.md").exists()
        assert not (sync_workspace / ".antigravity" / "rules" / "test.md").exists()
        assert not (sync_workspace / ".codex" / "rules" / "test.md").exists()

    def test_sync_skips_all_when_no_manifest(self, sync_workspace):
        """When no manifest exists, sync skips all tools (not installed)."""
        sources: dict[str, tuple[Path, dict, str]] = {
            "test.md": (Path(), {}, "Test content.\n"),
        }
        sync_to_all_tools(sources, "rules_dir", _noop_transform, "Rules")

        # No tools should have the file  - no manifest means not installed
        for tool in Tool:
            assert not (
                sync_workspace / f".{tool.value}" / "rules" / "test.md"
            ).exists()

    def test_sync_multiple_providers(self, sync_workspace):
        """When manifest has multiple providers, all get synced."""
        write_manifest(sync_workspace, {"claude", "gemini"})

        sources: dict[str, tuple[Path, dict, str]] = {
            "test.md": (Path(), {}, "Test content.\n"),
        }
        sync_to_all_tools(sources, "rules_dir", _noop_transform, "Rules")

        assert (sync_workspace / ".claude" / "rules" / "test.md").exists()
        assert (sync_workspace / ".gemini" / "rules" / "test.md").exists()
        assert not (sync_workspace / ".antigravity" / "rules" / "test.md").exists()
