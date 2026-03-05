"""Collect/transform/listing/assembly tests for the CLI sync engine.

Covers: collect_rules, collect_agents, collect_skills, collect_system_parts,
transform_rule, transform_agent, transform_skill, listings,
_generate_config, _generate_system_prompt.
"""

from __future__ import annotations

import shutil

import pytest

import vaultspec.core.types as _types
from vaultspec.core import (
    collect_agents,
    collect_rules,
    collect_skills,
    transform_agent,
    transform_rule,
    transform_skill,
)
from vaultspec.core.config_gen import _generate_config
from vaultspec.core.enums import Tool
from vaultspec.core.system import (
    _collect_agent_listing,
    _collect_skill_listing,
    _generate_system_prompt,
    _generate_system_rules,
    collect_system_parts,
)
from vaultspec.core.types import CONFIG_HEADER, ToolConfig
from vaultspec.protocol.providers import ClaudeModels
from vaultspec.vaultcore import parse_frontmatter

from .conftest import TEST_PROJECT

pytestmark = [pytest.mark.unit]


class TestCollectRules:
    def test_builtin_and_custom(self):
        """Both .builtin.md and plain .md files are collected from rules/rules/."""
        (TEST_PROJECT / ".vaultspec" / "rules" / "rules" / "a.builtin.md").write_text(
            "---\nname: a\n---\n\nBuilt-in A", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules" / "rules" / "b.md").write_text(
            "---\nname: b\n---\n\nCustom B", encoding="utf-8"
        )
        sources = collect_rules()
        assert "a.builtin.md" in sources
        assert "b.md" in sources

    def test_empty_dirs(self):
        # dirs exist but are empty
        sources = collect_rules()
        assert sources == {}

    def test_missing_dirs(self):
        shutil.rmtree(TEST_PROJECT / ".vaultspec" / "rules")
        sources = collect_rules()
        assert sources == {}

    def test_builtin_suffix_detected(self):
        """Builtin rules use .builtin.md suffix; custom rules use plain .md."""
        (
            TEST_PROJECT / ".vaultspec" / "rules" / "rules" / "core.builtin.md"
        ).write_text("---\nname: core\n---\n\nBuilt-in content", encoding="utf-8")
        (TEST_PROJECT / ".vaultspec" / "rules" / "rules" / "custom.md").write_text(
            "---\nname: custom\n---\n\nCustom content", encoding="utf-8"
        )
        sources = collect_rules()
        assert "core.builtin.md" in sources
        assert "custom.md" in sources


class TestCollectAgents:
    def test_valid_frontmatter(self):
        (TEST_PROJECT / ".vaultspec" / "rules" / "agents" / "coder.md").write_text(
            "---\ndescription: A coder\ntier: HIGH\n---\n\n# Coder",
            encoding="utf-8",
        )
        agents = collect_agents()
        assert "coder.md" in agents
        _path, meta, _body = agents["coder.md"]
        assert meta["tier"] == "HIGH"
        assert meta["description"] == "A coder"

    def test_missing_agents_dir(self):
        shutil.rmtree(TEST_PROJECT / ".vaultspec" / "rules" / "agents")
        assert collect_agents() == {}


class TestCollectSkills:
    def test_filters_task_prefix(self):
        deploy_dir = (
            TEST_PROJECT / ".vaultspec" / "rules" / "skills" / "vaultspec-deploy"
        )
        deploy_dir.mkdir(parents=True, exist_ok=True)
        (deploy_dir / "SKILL.md").write_text(
            "---\ndescription: Deploy\n---\n\n# Deploy", encoding="utf-8"
        )
        helper_dir = TEST_PROJECT / ".vaultspec" / "rules" / "skills" / "utility-helper"
        helper_dir.mkdir(parents=True, exist_ok=True)
        (helper_dir / "SKILL.md").write_text(
            "---\ndescription: Helper\n---\n\n# Helper", encoding="utf-8"
        )
        skills = collect_skills()
        assert "vaultspec-deploy" in skills
        assert "utility-helper" not in skills

    def test_empty_skills_dir(self):
        assert collect_skills() == {}


class TestCollectSystemParts:
    def test_with_tool_filter(self):
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base prompt", encoding="utf-8"
        )
        (
            TEST_PROJECT / ".vaultspec" / "rules" / "system" / "gemini-extra.md"
        ).write_text("---\ntool: gemini\n---\n\n# Gemini only", encoding="utf-8")
        parts = collect_system_parts()
        assert "base" in parts
        assert "gemini-extra" in parts
        _path, meta, _body = parts["gemini-extra"]
        assert meta["tool"] == "gemini"

    def test_missing_dir(self):
        shutil.rmtree(TEST_PROJECT / ".vaultspec" / "rules" / "system")
        assert collect_system_parts() == {}


class TestTransformRule:
    def test_claude_includes_name(self):
        out = transform_rule(Tool.CLAUDE, "my-rule.md", {}, "Body text")
        meta, body = parse_frontmatter(out)
        assert meta["name"] == "my-rule"
        assert meta["trigger"] == "always_on"
        assert "Body text" in body

    def test_agent_no_name(self):
        out = transform_rule(Tool.AGENTS, "my-rule.md", {}, "Body")
        meta, _body = parse_frontmatter(out)
        assert "name" not in meta
        assert meta["trigger"] == "always_on"

    def test_gemini_includes_name(self):
        out = transform_rule(Tool.GEMINI, "rule.md", {}, "Content")
        meta, _body = parse_frontmatter(out)
        assert meta["name"] == "rule"


class TestTransformAgent:
    def test_valid_model(self):
        result = transform_agent(
            Tool.CLAUDE,
            "coder.md",
            {"description": "A coder", "model": ClaudeModels.HIGH},
            "Body",
        )
        assert result is not None
        meta, body = parse_frontmatter(result)
        assert meta["model"] == str(ClaudeModels.HIGH)
        assert meta["name"] == "coder"
        assert "Body" in body

    def test_missing_model_uses_default(self):
        result = transform_agent(Tool.CLAUDE, "agent.md", {"description": "x"}, "Body")
        assert result is not None
        meta, body = parse_frontmatter(result)
        assert meta["model"] == str(ClaudeModels.MEDIUM)


class TestTransformSkill:
    def test_extracts_description(self):
        out = transform_skill(
            Tool.CLAUDE, "vaultspec-deploy", {"description": "Deploy things"}, "# Deploy"
        )
        meta, body = parse_frontmatter(out)
        assert meta["description"] == "Deploy things"
        assert meta["name"] == "vaultspec-deploy"
        assert "# Deploy" in body


class TestListings:
    def test_agent_listing_format(self):
        (TEST_PROJECT / ".vaultspec" / "rules" / "agents" / "coder.md").write_text(
            "---\ndescription: Writes code\ntier: HIGH\n---\n\nbody",
            encoding="utf-8",
        )
        listing = _collect_agent_listing()
        assert "## Available Sub-Agents" in listing
        assert "coder" in listing
        assert "Writes code" in listing

    def test_agent_listing_empty(self):
        listing = _collect_agent_listing()
        assert listing == ""

    def test_skill_listing_format(self):
        deploy_dir = (
            TEST_PROJECT / ".vaultspec" / "rules" / "skills" / "vaultspec-deploy"
        )
        deploy_dir.mkdir(parents=True, exist_ok=True)
        (deploy_dir / "SKILL.md").write_text(
            "---\ndescription: Deploy things\n---\n\nbody",
            encoding="utf-8",
        )
        listing = _collect_skill_listing()
        assert "## Available Skills" in listing
        assert "**vaultspec-deploy**" in listing
        assert "Deploy things" in listing

    def test_skill_listing_empty(self):
        listing = _collect_skill_listing()
        assert listing == ""


class TestGenerateConfig:
    def test_internal_and_custom(self):
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "Internal body", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "project.md").write_text(
            "Custom body", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_config(cfg)
        assert content is not None
        assert CONFIG_HEADER in content
        assert "Custom body" in content

    def test_internal_only(self):
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "Internal body", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_config(cfg)
        assert content is not None
        assert CONFIG_HEADER in content

    def test_returns_none_without_internal(self):
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_config(cfg)
        assert content is None

    def test_includes_rule_references(self):
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "Internal", encoding="utf-8"
        )
        # Create a synced rule in the destination
        (TEST_PROJECT / ".claude" / "rules" / "my-rule.md").write_text(
            "rule content", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_config(cfg)
        assert content is not None
        assert "@rules/my-rule.md" in content


class TestGenerateSystemPrompt:
    def test_assembly_order(self):
        # base comes first
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE CONTENT", encoding="utf-8"
        )
        # tool-specific next
        (
            TEST_PROJECT / ".vaultspec" / "rules" / "system" / "gemini-tools.md"
        ).write_text("---\ntool: gemini\n---\n\n# GEMINI TOOLS", encoding="utf-8")
        # shared last
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "zzz-shared.md").write_text(
            "---\n---\n\n# SHARED CONTENT", encoding="utf-8"
        )

        cfg = _types.TOOL_CONFIGS["gemini"]
        content = _generate_system_prompt(cfg)
        assert content is not None

        # Verify ordering: base -> tool-specific -> shared
        base_pos = content.index("# BASE CONTENT")
        tool_pos = content.index("# GEMINI TOOLS")
        shared_pos = content.index("# SHARED CONTENT")
        assert base_pos < tool_pos < shared_pos

    def test_missing_base(self):
        # Only a shared part, no base.md
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "extra.md").write_text(
            "---\n---\n\n# Extra", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["gemini"]
        content = _generate_system_prompt(cfg)
        assert content is not None
        assert "# Extra" in content

    def test_multiple_tool_specific_parts(self):
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "gemini-a.md").write_text(
            "---\ntool: gemini\n---\n\n# Gemini A", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "gemini-b.md").write_text(
            "---\ntool: gemini\n---\n\n# Gemini B", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["gemini"]
        content = _generate_system_prompt(cfg)
        assert content is not None
        assert "# Gemini A" in content
        assert "# Gemini B" in content

    def test_returns_none_for_no_system_file(self):
        cfg = _types.TOOL_CONFIGS["claude"]  # claude has system_file=None
        content = _generate_system_prompt(cfg)
        assert content is None

    def test_returns_none_for_empty_parts(self):
        shutil.rmtree(TEST_PROJECT / ".vaultspec" / "rules" / "system")
        cfg = _types.TOOL_CONFIGS["gemini"]
        content = _generate_system_prompt(cfg)
        assert content is None

    def test_order_frontmatter_respected(self):
        """Files with lower order appear before files with higher/default order."""
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        # workflow has order: 20 (should appear first among shared)
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "workflow.md").write_text(
            "---\norder: 20\n---\n\n# WORKFLOW", encoding="utf-8"
        )
        # operations has no order (defaults to 50, should appear after workflow)
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "operations.md").write_text(
            "---\n---\n\n# OPERATIONS", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["gemini"]
        content = _generate_system_prompt(cfg)
        assert content is not None
        workflow_pos = content.index("# WORKFLOW")
        operations_pos = content.index("# OPERATIONS")
        assert workflow_pos < operations_pos

    def test_pipeline_config_excluded(self):
        """Parts with pipeline: config are excluded from system prompt."""
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "---\npipeline: config\n---\n\n# FRAMEWORK CONFIG", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["gemini"]
        content = _generate_system_prompt(cfg)
        assert content is not None
        assert "# BASE" in content
        assert "# FRAMEWORK CONFIG" not in content

    def test_includes_agent_listing(self):
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules" / "agents" / "coder.md").write_text(
            "---\ndescription: Writes code\ntier: HIGH\n---\n\nbody",
            encoding="utf-8",
        )
        cfg = _types.TOOL_CONFIGS["gemini"]
        content = _generate_system_prompt(cfg)
        assert content is not None
        assert "## Available Sub-Agents" in content
        assert "coder" in content

    def test_includes_skill_listing(self):
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )
        deploy_dir = (
            TEST_PROJECT / ".vaultspec" / "rules" / "skills" / "vaultspec-deploy"
        )
        deploy_dir.mkdir(parents=True, exist_ok=True)
        (deploy_dir / "SKILL.md").write_text(
            "---\ndescription: Deploy service\n---\n\n# Deploy",
            encoding="utf-8",
        )
        cfg = _types.TOOL_CONFIGS["gemini"]
        content = _generate_system_prompt(cfg)
        assert content is not None
        assert "## Available Skills" in content
        assert "**vaultspec-deploy**" in content


class TestGenerateSystemRules:
    def test_generates_for_tool_without_system_file(self):
        """Claude (rules_dir but no system_file) gets behavioral rules."""
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE MANDATES", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "operations.md").write_text(
            "---\n---\n\n# OPERATIONS", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_system_rules(cfg)
        assert content is not None
        assert "# BASE MANDATES" in content
        assert "# OPERATIONS" in content
        meta, _body = parse_frontmatter(content.replace(CONFIG_HEADER + "\n", ""))
        assert meta["name"] == "vaultspec-system"
        assert meta["trigger"] == "always_on"

    def test_excludes_tool_specific_parts(self):
        """Behavioral rules exclude tool-specific parts."""
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        (
            TEST_PROJECT / ".vaultspec" / "rules" / "system" / "gemini-tools.md"
        ).write_text("---\ntool: gemini\n---\n\n# GEMINI ONLY", encoding="utf-8")
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "shared.md").write_text(
            "---\n---\n\n# SHARED", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_system_rules(cfg)
        assert content is not None
        assert "# BASE" in content
        assert "# SHARED" in content
        assert "# GEMINI ONLY" not in content

    def test_excludes_pipeline_config(self):
        """Behavioral rules exclude pipeline: config parts."""
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "---\npipeline: config\n---\n\n# CONFIG ONLY", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_system_rules(cfg)
        assert content is not None
        assert "# BASE" in content
        assert "# CONFIG ONLY" not in content

    def test_returns_none_without_rules_dir(self):
        """ToolConfig with no rules_dir returns None."""
        cfg = ToolConfig(name="test", rules_dir=None, agents_dir=None, skills_dir=None)
        content = _generate_system_rules(cfg)
        assert content is None

    def test_returns_none_for_empty_parts(self):
        shutil.rmtree(TEST_PROJECT / ".vaultspec" / "rules" / "system")
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_system_rules(cfg)
        assert content is None

    def test_order_frontmatter_respected(self):
        """Order frontmatter controls assembly order in rules too."""
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "workflow.md").write_text(
            "---\norder: 20\n---\n\n# WORKFLOW", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "operations.md").write_text(
            "---\n---\n\n# OPERATIONS", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_system_rules(cfg)
        assert content is not None
        workflow_pos = content.index("# WORKFLOW")
        operations_pos = content.index("# OPERATIONS")
        assert workflow_pos < operations_pos
