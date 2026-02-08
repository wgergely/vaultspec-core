"""Tests for resolve_includes() in both Claude and Gemini providers."""

from __future__ import annotations

import pathlib

import pytest

from agent_providers.claude import ClaudeProvider
from agent_providers.gemini import GeminiProvider


@pytest.fixture(params=["claude", "gemini"], ids=["claude", "gemini"])
def provider(request):
    """Parametrized fixture: runs each test against both providers."""
    if request.param == "claude":
        return ClaudeProvider()
    return GeminiProvider()


@pytest.fixture
def workspace(tmp_path):
    """Minimal workspace for include resolution tests."""
    (tmp_path / "rules").mkdir()
    (tmp_path / ".agent" / "rules").mkdir(parents=True)
    return tmp_path


class TestResolveIncludes:
    def test_resolve_relative_to_base_dir(self, provider, workspace):
        (workspace / "rules" / "foo.md").write_text("Foo content.\n", encoding="utf-8")

        content = "@foo.md"
        result = provider.resolve_includes(content, workspace / "rules", workspace)
        assert "Foo content." in result

    def test_resolve_fallback_to_root_dir(self, provider, workspace):
        (workspace / "rules" / "bar.md").write_text("Bar content.\n", encoding="utf-8")

        # base_dir is a different subdirectory — file not found there
        other = workspace / "other"
        other.mkdir()
        content = "@rules/bar.md"
        result = provider.resolve_includes(content, other, workspace)
        assert "Bar content." in result

    def test_resolve_dotted_directory(self, provider, workspace):
        """Regression: lstrip('./') used to eat leading dots from .agent/."""
        (workspace / ".agent" / "rules" / "dotted.md").write_text(
            "Dotted content.\n", encoding="utf-8"
        )

        content = "@.agent/rules/dotted.md"
        result = provider.resolve_includes(content, workspace, workspace)
        assert "Dotted content." in result

    def test_resolve_missing_include(self, provider, workspace):
        content = "@nonexistent/file.md"
        result = provider.resolve_includes(content, workspace, workspace)
        assert "<!-- ERROR: Missing include: nonexistent/file.md -->" in result

    def test_resolve_outside_workspace(self, provider, workspace):
        # Create a file outside workspace
        outside = workspace.parent / "outside.md"
        outside.write_text("Secret.\n", encoding="utf-8")

        content = f"@{outside}"
        result = provider.resolve_includes(content, workspace, workspace)
        assert "ERROR" in result

    def test_resolve_recursive(self, provider, workspace):
        (workspace / "rules" / "inner.md").write_text("Inner text.\n", encoding="utf-8")
        (workspace / "rules" / "outer.md").write_text(
            "Outer start.\n@inner.md\nOuter end.\n", encoding="utf-8"
        )

        content = "@rules/outer.md"
        result = provider.resolve_includes(content, workspace, workspace)
        assert "Outer start." in result
        assert "Inner text." in result
        assert "Outer end." in result

    def test_resolve_backslash_paths(self, provider, workspace):
        (workspace / "rules" / "win.md").write_text("Windows path.\n", encoding="utf-8")

        content = "@rules\\win.md"
        result = provider.resolve_includes(content, workspace, workspace)
        assert "Windows path." in result

    def test_resolve_skips_urls(self, provider, workspace):
        content = "@https://example.com/foo.md\nNormal line."
        result = provider.resolve_includes(content, workspace, workspace)
        assert "@https://example.com/foo.md" in result
        assert "Normal line." in result

    def test_passthrough_non_include_lines(self, provider, workspace):
        content = "# Title\n\nRegular paragraph.\n"
        result = provider.resolve_includes(content, workspace, workspace)
        assert "# Title" in result
        assert "Regular paragraph." in result
