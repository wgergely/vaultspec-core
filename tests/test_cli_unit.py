"""Unit tests for cli.py pure functions (no filesystem side-effects)."""

from __future__ import annotations

import pathlib

import pytest

import cli as cli_mod


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_basic(self):
        content = "---\nname: foo\ntrigger: always_on\n---\n\n# Body\n"
        meta, body = cli_mod.parse_frontmatter(content)
        assert meta["name"] == "foo"
        assert meta["trigger"] == "always_on"
        assert "# Body" in body

    def test_no_frontmatter(self):
        content = "# Just a heading\n\nSome text.\n"
        meta, body = cli_mod.parse_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_empty_body(self):
        content = "---\nname: bar\n---\n"
        meta, body = cli_mod.parse_frontmatter(content)
        assert meta["name"] == "bar"
        assert body.strip() == ""

    def test_multiline_body(self):
        content = "---\nkey: val\n---\n\nLine 1\nLine 2\nLine 3\n"
        meta, body = cli_mod.parse_frontmatter(content)
        assert meta["key"] == "val"
        assert "Line 1" in body
        assert "Line 3" in body


# ---------------------------------------------------------------------------
# build_file
# ---------------------------------------------------------------------------


class TestBuildFile:
    def test_basic(self):
        result = cli_mod.build_file({"name": "test"}, "# Hello\n")
        assert result.startswith("---\n")
        assert "name: test" in result
        assert result.endswith("\n\n# Hello\n")

    def test_roundtrip(self):
        fm = {"name": "roundtrip", "trigger": "always_on"}
        body = "# My rule\n\nSome instructions.\n"
        built = cli_mod.build_file(fm, body)
        parsed_fm, parsed_body = cli_mod.parse_frontmatter(built)
        assert parsed_fm["name"] == "roundtrip"
        assert parsed_fm["trigger"] == "always_on"
        assert "Some instructions." in parsed_body


# ---------------------------------------------------------------------------
# transform_rule
# ---------------------------------------------------------------------------


class TestTransformRule:
    def test_claude_gets_name(self):
        result = cli_mod.transform_rule("claude", "my-rule.md", {}, "body\n")
        meta, body = cli_mod.parse_frontmatter(result)
        assert meta["name"] == "my-rule"
        assert meta["trigger"] == "always_on"
        assert "body" in body

    def test_gemini_gets_name(self):
        result = cli_mod.transform_rule("gemini", "my-rule.md", {}, "body\n")
        meta, _ = cli_mod.parse_frontmatter(result)
        assert "name" in meta

    def test_antigravity_no_name(self):
        result = cli_mod.transform_rule("antigravity", "my-rule.md", {}, "body\n")
        meta, _ = cli_mod.parse_frontmatter(result)
        assert "name" not in meta
        assert meta["trigger"] == "always_on"


# ---------------------------------------------------------------------------
# transform_agent
# ---------------------------------------------------------------------------


class TestTransformAgent:
    def test_basic_with_tier(self):
        meta = {"description": "Test agent", "tier": "MEDIUM"}
        result = cli_mod.transform_agent("claude", "test-agent.md", meta, "# Persona\n")
        assert result is not None
        parsed_fm, parsed_body = cli_mod.parse_frontmatter(result)
        assert parsed_fm["name"] == "test-agent"
        assert parsed_fm["description"] == "Test agent"
        assert parsed_fm["kind"] == "local"
        assert parsed_fm["model"] == "claude-sonnet-4-5"
        assert "# Persona" in parsed_body

    def test_missing_tier_returns_none(self):
        meta = {"description": "No tier agent"}
        result = cli_mod.transform_agent("claude", "bad.md", meta, "body\n")
        assert result is None

    def test_gemini_model_resolution(self):
        meta = {"description": "G agent", "tier": "HIGH"}
        result = cli_mod.transform_agent("gemini", "g-agent.md", meta, "body\n")
        assert result is not None
        parsed_fm, _ = cli_mod.parse_frontmatter(result)
        assert parsed_fm["model"] == "gemini-3-pro-preview"


# ---------------------------------------------------------------------------
# transform_skill
# ---------------------------------------------------------------------------


class TestTransformSkill:
    def test_basic(self):
        meta = {"description": "My skill description"}
        result = cli_mod.transform_skill("claude", "task-foo", meta, "# Instructions\n")
        parsed_fm, parsed_body = cli_mod.parse_frontmatter(result)
        assert parsed_fm["name"] == "task-foo"
        assert parsed_fm["description"] == "My skill description"
        assert "# Instructions" in parsed_body


# ---------------------------------------------------------------------------
# skill_dest_path
# ---------------------------------------------------------------------------


class TestSkillDestPath:
    def test_returns_subdir_with_skill_md(self):
        dest_dir = pathlib.Path("/some/skills")
        result = cli_mod.skill_dest_path(dest_dir, "task-write")
        assert result == dest_dir / "task-write" / "SKILL.md"


# ---------------------------------------------------------------------------
# _is_cli_managed
# ---------------------------------------------------------------------------


class TestIsCliManaged:
    def test_managed_file(self, tmp_path):
        f = tmp_path / "CLAUDE.md"
        f.write_text(f"{cli_mod.CONFIG_HEADER}\n\n# Content\n", encoding="utf-8")
        assert cli_mod._is_cli_managed(f) is True

    def test_custom_file(self, tmp_path):
        f = tmp_path / "CLAUDE.md"
        f.write_text("# My custom config\n\nHand-written stuff.\n", encoding="utf-8")
        assert cli_mod._is_cli_managed(f) is False

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "NOPE.md"
        assert cli_mod._is_cli_managed(f) is False


# ---------------------------------------------------------------------------
# resolve_model
# ---------------------------------------------------------------------------


class TestResolveModel:
    @pytest.mark.parametrize(
        "tool,tier,expected",
        [
            ("claude", "LOW", "claude-haiku-4-5"),
            ("claude", "MEDIUM", "claude-sonnet-4-5"),
            ("claude", "HIGH", "claude-opus-4-6"),
            ("gemini", "LOW", "gemini-2.5-flash"),
            ("gemini", "MEDIUM", "gemini-3-flash-preview"),
            ("gemini", "HIGH", "gemini-3-pro-preview"),
        ],
    )
    def test_tier_resolution(self, tool, tier, expected):
        result = cli_mod.resolve_model(tool, tier)
        assert result == expected

    def test_invalid_tier(self):
        result = cli_mod.resolve_model("claude", "BOGUS")
        assert result is None

    def test_unknown_tool(self):
        result = cli_mod.resolve_model("nonexistent", "LOW")
        assert result is None
