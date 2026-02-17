"""Collect/transform/listing/assembly tests for the CLI sync engine.

Covers: collect_rules, collect_agents, collect_skills, collect_system_parts,
transform_rule, transform_agent, transform_skill, listings,
_generate_config, _generate_system_prompt.
"""

from __future__ import annotations

import shutil

import cli
import pytest

from protocol.providers.base import ClaudeModels

from .conftest import TEST_PROJECT

pytestmark = [pytest.mark.unit]


class TestCollectRules:
    def test_builtin_and_custom(self):
        """Both .builtin.md and plain .md files are collected from rules/."""
        (TEST_PROJECT / ".vaultspec" / "rules" / "a.builtin.md").write_text(
            "---\nname: a\n---\n\nBuilt-in A", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules" / "b.md").write_text(
            "---\nname: b\n---\n\nCustom B", encoding="utf-8"
        )
        sources = cli.collect_rules()
        assert "a.builtin.md" in sources
        assert "b.md" in sources

    def test_empty_dirs(self):
        # dirs exist but are empty
        sources = cli.collect_rules()
        assert sources == {}

    def test_missing_dirs(self):
        shutil.rmtree(TEST_PROJECT / ".vaultspec" / "rules")
        sources = cli.collect_rules()
        assert sources == {}

    def test_builtin_suffix_detected(self):
        """Builtin rules use .builtin.md suffix; custom rules use plain .md."""
        (TEST_PROJECT / ".vaultspec" / "rules" / "core.builtin.md").write_text(
            "---\nname: core\n---\n\nBuilt-in content", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules" / "custom.md").write_text(
            "---\nname: custom\n---\n\nCustom content", encoding="utf-8"
        )
        sources = cli.collect_rules()
        assert "core.builtin.md" in sources
        assert "custom.md" in sources


class TestCollectAgents:
    def test_valid_frontmatter(self):
        (TEST_PROJECT / ".vaultspec" / "agents" / "coder.md").write_text(
            "---\ndescription: A coder\ntier: HIGH\n---\n\n# Coder",
            encoding="utf-8",
        )
        agents = cli.collect_agents()
        assert "coder.md" in agents
        _path, meta, _body = agents["coder.md"]
        assert meta["tier"] == "HIGH"
        assert meta["description"] == "A coder"

    def test_missing_agents_dir(self):
        shutil.rmtree(TEST_PROJECT / ".vaultspec" / "agents")
        assert cli.collect_agents() == {}


class TestCollectSkills:
    def test_filters_task_prefix(self):
        (TEST_PROJECT / ".vaultspec" / "skills" / "vaultspec-deploy.md").write_text(
            "---\ndescription: Deploy\n---\n\n# Deploy", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "skills" / "utility-helper.md").write_text(
            "---\ndescription: Helper\n---\n\n# Helper", encoding="utf-8"
        )
        skills = cli.collect_skills()
        assert "vaultspec-deploy" in skills
        assert "utility-helper" not in skills

    def test_empty_skills_dir(self):
        assert cli.collect_skills() == {}


class TestCollectSystemParts:
    def test_with_tool_filter(self):
        (TEST_PROJECT / ".vaultspec" / "system" / "base.md").write_text(
            "---\n---\n\n# Base prompt", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "system" / "gemini-extra.md").write_text(
            "---\ntool: gemini\n---\n\n# Gemini only", encoding="utf-8"
        )
        parts = cli.collect_system_parts()
        assert "base" in parts
        assert "gemini-extra" in parts
        _path, meta, _body = parts["gemini-extra"]
        assert meta["tool"] == "gemini"

    def test_missing_dir(self):
        shutil.rmtree(TEST_PROJECT / ".vaultspec" / "system")
        assert cli.collect_system_parts() == {}


class TestTransformRule:
    def test_claude_includes_name(self):
        out = cli.transform_rule("claude", "my-rule.md", {}, "Body text")
        meta, body = cli.parse_frontmatter(out)
        assert meta["name"] == "my-rule"
        assert meta["trigger"] == "always_on"
        assert "Body text" in body

    def test_antigravity_no_name(self):
        out = cli.transform_rule("antigravity", "my-rule.md", {}, "Body")
        meta, _body = cli.parse_frontmatter(out)
        assert "name" not in meta
        assert meta["trigger"] == "always_on"

    def test_gemini_includes_name(self):
        out = cli.transform_rule("gemini", "rule.md", {}, "Content")
        meta, _body = cli.parse_frontmatter(out)
        assert meta["name"] == "rule"


class TestTransformAgent:
    def test_valid_tier(self):
        result = cli.transform_agent(
            "claude",
            "coder.md",
            {"description": "A coder", "tier": "HIGH"},
            "Body",
        )
        assert result is not None
        meta, body = cli.parse_frontmatter(result)
        assert meta["model"] == ClaudeModels.HIGH
        assert meta["name"] == "coder"
        assert "Body" in body

    def test_missing_model_returns_none(self):
        result = cli.transform_agent(
            "claude",
            "agent.md",
            {"description": "x", "tier": "HIGH"},
            "Body",
            resolve_fn=lambda *_args, **_kw: None,
        )
        assert result is None

    def test_missing_tier_returns_none(self):
        result = cli.transform_agent("claude", "agent.md", {"description": "x"}, "Body")
        assert result is None


class TestTransformSkill:
    def test_extracts_description(self):
        out = cli.transform_skill(
            "claude", "vaultspec-deploy", {"description": "Deploy things"}, "# Deploy"
        )
        meta, body = cli.parse_frontmatter(out)
        assert meta["description"] == "Deploy things"
        assert meta["name"] == "vaultspec-deploy"
        assert "# Deploy" in body


class TestListings:
    def test_agent_listing_format(self):
        (TEST_PROJECT / ".vaultspec" / "agents" / "coder.md").write_text(
            "---\ndescription: Writes code\ntier: HIGH\n---\n\nbody",
            encoding="utf-8",
        )
        listing = cli._collect_agent_listing()
        assert "## Available Sub-Agents" in listing
        assert "**coder**" in listing
        assert "HIGH" in listing
        assert "Writes code" in listing

    def test_agent_listing_empty(self):
        listing = cli._collect_agent_listing()
        assert listing == ""

    def test_skill_listing_format(self):
        (TEST_PROJECT / ".vaultspec" / "skills" / "vaultspec-deploy.md").write_text(
            "---\ndescription: Deploy things\n---\n\nbody",
            encoding="utf-8",
        )
        listing = cli._collect_skill_listing()
        assert "## Available Skills" in listing
        assert "**vaultspec-deploy**" in listing
        assert "Deploy things" in listing

    def test_skill_listing_empty(self):
        listing = cli._collect_skill_listing()
        assert listing == ""


class TestGenerateConfig:
    def test_internal_and_custom(self):
        (TEST_PROJECT / ".vaultspec" / "system" / "framework.md").write_text(
            "Internal body", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "system" / "project.md").write_text(
            "Custom body", encoding="utf-8"
        )
        cfg = cli.TOOL_CONFIGS["claude"]
        content = cli._generate_config(cfg)
        assert content is not None
        assert cli.CONFIG_HEADER in content
        assert "Custom body" in content

    def test_internal_only(self):
        (TEST_PROJECT / ".vaultspec" / "system" / "framework.md").write_text(
            "Internal body", encoding="utf-8"
        )
        cfg = cli.TOOL_CONFIGS["claude"]
        content = cli._generate_config(cfg)
        assert content is not None
        assert cli.CONFIG_HEADER in content

    def test_returns_none_without_internal(self):
        cfg = cli.TOOL_CONFIGS["claude"]
        content = cli._generate_config(cfg)
        assert content is None

    def test_includes_rule_references(self):
        (TEST_PROJECT / ".vaultspec" / "system" / "framework.md").write_text(
            "Internal", encoding="utf-8"
        )
        # Create a synced rule in the destination
        (TEST_PROJECT / ".claude" / "rules" / "my-rule.md").write_text(
            "rule content", encoding="utf-8"
        )
        cfg = cli.TOOL_CONFIGS["claude"]
        content = cli._generate_config(cfg)
        assert content is not None
        assert "@rules/my-rule.md" in content


class TestGenerateSystemPrompt:
    def test_assembly_order(self):
        # base comes first
        (TEST_PROJECT / ".vaultspec" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE CONTENT", encoding="utf-8"
        )
        # tool-specific next
        (TEST_PROJECT / ".vaultspec" / "system" / "gemini-tools.md").write_text(
            "---\ntool: gemini\n---\n\n# GEMINI TOOLS", encoding="utf-8"
        )
        # shared last
        (TEST_PROJECT / ".vaultspec" / "system" / "zzz-shared.md").write_text(
            "---\n---\n\n# SHARED CONTENT", encoding="utf-8"
        )

        cfg = cli.TOOL_CONFIGS["gemini"]
        content = cli._generate_system_prompt(cfg)
        assert content is not None

        # Verify ordering: base -> tool-specific -> shared
        base_pos = content.index("# BASE CONTENT")
        tool_pos = content.index("# GEMINI TOOLS")
        shared_pos = content.index("# SHARED CONTENT")
        assert base_pos < tool_pos < shared_pos

    def test_missing_base(self):
        # Only a shared part, no base.md
        (TEST_PROJECT / ".vaultspec" / "system" / "extra.md").write_text(
            "---\n---\n\n# Extra", encoding="utf-8"
        )
        cfg = cli.TOOL_CONFIGS["gemini"]
        content = cli._generate_system_prompt(cfg)
        assert content is not None
        assert "# Extra" in content

    def test_multiple_tool_specific_parts(self):
        (TEST_PROJECT / ".vaultspec" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "system" / "gemini-a.md").write_text(
            "---\ntool: gemini\n---\n\n# Gemini A", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "system" / "gemini-b.md").write_text(
            "---\ntool: gemini\n---\n\n# Gemini B", encoding="utf-8"
        )
        cfg = cli.TOOL_CONFIGS["gemini"]
        content = cli._generate_system_prompt(cfg)
        assert content is not None
        assert "# Gemini A" in content
        assert "# Gemini B" in content

    def test_returns_none_for_no_system_file(self):
        cfg = cli.TOOL_CONFIGS["claude"]  # claude has system_file=None
        content = cli._generate_system_prompt(cfg)
        assert content is None

    def test_returns_none_for_empty_parts(self):
        shutil.rmtree(TEST_PROJECT / ".vaultspec" / "system")
        cfg = cli.TOOL_CONFIGS["gemini"]
        content = cli._generate_system_prompt(cfg)
        assert content is None

    def test_includes_agent_listing(self):
        (TEST_PROJECT / ".vaultspec" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "agents" / "coder.md").write_text(
            "---\ndescription: Writes code\ntier: HIGH\n---\n\nbody",
            encoding="utf-8",
        )
        cfg = cli.TOOL_CONFIGS["gemini"]
        content = cli._generate_system_prompt(cfg)
        assert content is not None
        assert "## Available Sub-Agents" in content
        assert "**coder**" in content

    def test_includes_skill_listing(self):
        (TEST_PROJECT / ".vaultspec" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "skills" / "vaultspec-deploy.md").write_text(
            "---\ndescription: Deploy service\n---\n\n# Deploy",
            encoding="utf-8",
        )
        cfg = cli.TOOL_CONFIGS["gemini"]
        content = cli._generate_system_prompt(cfg)
        assert content is not None
        assert "## Available Skills" in content
        assert "**vaultspec-deploy**" in content
