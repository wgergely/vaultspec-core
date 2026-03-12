"""Collect/transform/listing/assembly tests for the CLI sync engine.

Covers: collect_rules, collect_skills, collect_system_parts,
transform_rule, transform_skill, listings,
_generate_config, _generate_system_prompt.
"""

from __future__ import annotations

import shutil

import pytest

import vaultspec_core.core.types as _types
from vaultspec_core.core import (
    collect_rules,
    collect_skills,
    transform_rule,
    transform_skill,
)
from vaultspec_core.core.config_gen import (
    _generate_codex_native_config,
    _generate_config,
)
from vaultspec_core.core.enums import Tool
from vaultspec_core.core.system import (
    _collect_skill_listing,
    _generate_system_prompt,
    _generate_system_rules,
    collect_system_parts,
)
from vaultspec_core.core.types import CONFIG_HEADER, ToolConfig
from vaultspec_core.vaultcore import parse_frontmatter

pytestmark = [pytest.mark.unit]


class TestCollectRules:
    def test_builtin_and_custom(self, test_project):
        """Both .builtin.md and plain .md files are collected from rules/rules/."""
        (test_project / ".vaultspec" / "rules" / "rules" / "a.builtin.md").write_text(
            "---\nname: a\n---\n\nBuilt-in A", encoding="utf-8"
        )
        (test_project / ".vaultspec" / "rules" / "rules" / "b.md").write_text(
            "---\nname: b\n---\n\nCustom B", encoding="utf-8"
        )
        sources = collect_rules()
        assert "a.builtin.md" in sources
        assert "b.md" in sources

    def test_empty_dirs(self, test_project):
        # dirs exist but are empty
        sources = collect_rules()
        assert sources == {}

    def test_missing_dirs(self, test_project):
        shutil.rmtree(test_project / ".vaultspec" / "rules")
        sources = collect_rules()
        assert sources == {}

    def test_builtin_suffix_detected(self, test_project):
        """Builtin rules use .builtin.md suffix; custom rules use plain .md."""
        (
            test_project / ".vaultspec" / "rules" / "rules" / "core.builtin.md"
        ).write_text("---\nname: core\n---\n\nBuilt-in content", encoding="utf-8")
        (test_project / ".vaultspec" / "rules" / "rules" / "custom.md").write_text(
            "---\nname: custom\n---\n\nCustom content", encoding="utf-8"
        )
        sources = collect_rules()
        assert "core.builtin.md" in sources
        assert "custom.md" in sources


class TestCollectSkills:
    def test_filters_task_prefix(self, test_project):
        deploy_dir = (
            test_project / ".vaultspec" / "rules" / "skills" / "vaultspec-deploy"
        )
        deploy_dir.mkdir(parents=True, exist_ok=True)
        (deploy_dir / "SKILL.md").write_text(
            "---\ndescription: Deploy\n---\n\n# Deploy", encoding="utf-8"
        )
        helper_dir = test_project / ".vaultspec" / "rules" / "skills" / "utility-helper"
        helper_dir.mkdir(parents=True, exist_ok=True)
        (helper_dir / "SKILL.md").write_text(
            "---\ndescription: Helper\n---\n\n# Helper", encoding="utf-8"
        )
        skills = collect_skills()
        assert "vaultspec-deploy" in skills
        assert "utility-helper" not in skills

    def test_empty_skills_dir(self, test_project):
        assert collect_skills() == {}


class TestCollectSystemParts:
    def test_with_tool_filter(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base prompt", encoding="utf-8"
        )
        (
            test_project / ".vaultspec" / "rules" / "system" / "gemini-extra.md"
        ).write_text("---\ntool: gemini\n---\n\n# Gemini only", encoding="utf-8")
        parts = collect_system_parts()
        assert "base" in parts
        assert "gemini-extra" in parts
        _path, meta, _body = parts["gemini-extra"]
        assert meta["tool"] == "gemini"

    def test_missing_dir(self, test_project):
        shutil.rmtree(test_project / ".vaultspec" / "rules" / "system")
        assert collect_system_parts() == {}


class TestTransformRule:
    def test_claude_includes_name(self, test_project):
        out = transform_rule(Tool.CLAUDE, "my-rule.md", {}, "Body text")
        meta, body = parse_frontmatter(out)
        assert meta["name"] == "my-rule"
        assert meta["trigger"] == "always_on"
        assert "Body text" in body

    def test_gemini_includes_name(self, test_project):
        out = transform_rule(Tool.GEMINI, "rule.md", {}, "Content")
        meta, _body = parse_frontmatter(out)
        assert meta["name"] == "rule"


class TestTransformSkill:
    def test_extracts_description(self, test_project):
        out = transform_skill(
            Tool.CLAUDE,
            "vaultspec-deploy",
            {"description": "Deploy things"},
            "# Deploy",
        )
        meta, _body = parse_frontmatter(out)
        assert meta["description"] == "Deploy things"
        assert meta["name"] == "vaultspec-deploy"


class TestListings:
    def test_skill_listing_format(self, test_project):
        deploy_dir = (
            test_project / ".vaultspec" / "rules" / "skills" / "vaultspec-deploy"
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

    def test_skill_listing_empty(self, test_project):
        listing = _collect_skill_listing()
        assert listing == ""


class TestGenerateConfig:
    def test_internal_and_custom(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "Internal body", encoding="utf-8"
        )
        (test_project / ".vaultspec" / "rules" / "system" / "project.md").write_text(
            "Custom body", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_config(cfg)
        assert content is not None
        assert CONFIG_HEADER in content
        assert "Custom body" in content

    def test_internal_only(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "Internal body", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_config(cfg)
        assert content is not None
        assert CONFIG_HEADER in content

    def test_returns_none_without_internal(self, test_project):
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_config(cfg)
        assert content is None

    def test_includes_rule_references(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "Internal", encoding="utf-8"
        )
        # Create a synced rule in the destination
        (test_project / ".claude" / "rules" / "my-rule.md").write_text(
            "rule content", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_config(cfg)
        assert content is not None
        assert "@rules/my-rule.md" in content

    def test_codex_does_not_generate_markdown_config(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "Internal", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["codex"]
        content = _generate_config(cfg)
        assert content is None

    def test_antigravity_uses_workspace_rules_for_root_gemini(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "Internal", encoding="utf-8"
        )
        (test_project / ".agents" / "rules").mkdir(parents=True, exist_ok=True)
        (test_project / ".agents" / "rules" / "workspace-rule.md").write_text(
            "rule content", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["antigravity"]
        content = _generate_config(cfg)
        assert content is not None
        assert "@.agents/rules/workspace-rule.md" in content

    def test_codex_native_config_uses_explicit_frontmatter(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "---\n"
            "codex_model: gpt-5-codex\n"
            "codex_approval_policy: on-request\n"
            "codex_project_root_markers:\n"
            "  - .git\n"
            "  - pyproject.toml\n"
            "---\n\nInternal",
            encoding="utf-8",
        )
        content = _generate_codex_native_config()
        assert content is not None
        assert 'model = "gpt-5-codex"' in content
        assert 'approval_policy = "on-request"' in content
        assert 'project_root_markers = [".git", "pyproject.toml"]' in content

    def test_codex_native_config_project_overrides_framework(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "---\ncodex_sandbox_mode: read-only\n---\n\nInternal",
            encoding="utf-8",
        )
        (test_project / ".vaultspec" / "rules" / "system" / "project.md").write_text(
            "---\ncodex_sandbox_mode: workspace-write\n---\n\nProject",
            encoding="utf-8",
        )
        content = _generate_codex_native_config()
        assert content is not None
        assert 'sandbox_mode = "workspace-write"' in content

    def test_codex_native_config_supports_reasoning_and_service_tier(
        self, test_project
    ):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "---\n"
            "codex_model_reasoning_effort: high\n"
            "codex_model_reasoning_summary: auto\n"
            "codex_model_supports_reasoning_summaries: true\n"
            "codex_model_verbosity: low\n"
            "codex_service_tier: flex\n"
            "---\n\nInternal",
            encoding="utf-8",
        )
        content = _generate_codex_native_config()
        assert content is not None
        assert 'model_reasoning_effort = "high"' in content
        assert 'model_reasoning_summary = "auto"' in content
        assert "model_supports_reasoning_summaries = true" in content
        assert 'model_verbosity = "low"' in content
        assert 'service_tier = "flex"' in content


class TestGenerateSystemPrompt:
    def test_assembly_order(self, test_project):
        # base comes first
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE CONTENT", encoding="utf-8"
        )
        # tool-specific next
        (
            test_project / ".vaultspec" / "rules" / "system" / "gemini-tools.md"
        ).write_text("---\ntool: gemini\n---\n\n# GEMINI TOOLS", encoding="utf-8")
        # shared last
        (test_project / ".vaultspec" / "rules" / "system" / "zzz-shared.md").write_text(
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

    def test_missing_base(self, test_project):
        # Only a shared part, no base.md
        (test_project / ".vaultspec" / "rules" / "system" / "extra.md").write_text(
            "---\n---\n\n# Extra", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["gemini"]
        content = _generate_system_prompt(cfg)
        assert content is not None
        assert "# Extra" in content

    def test_multiple_tool_specific_parts(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )
        (test_project / ".vaultspec" / "rules" / "system" / "gemini-a.md").write_text(
            "---\ntool: gemini\n---\n\n# Gemini A", encoding="utf-8"
        )
        (test_project / ".vaultspec" / "rules" / "system" / "gemini-b.md").write_text(
            "---\ntool: gemini\n---\n\n# Gemini B", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["gemini"]
        content = _generate_system_prompt(cfg)
        assert content is not None
        assert "# Gemini A" in content
        assert "# Gemini B" in content

    def test_returns_none_for_no_system_file(self, test_project):
        cfg = _types.TOOL_CONFIGS["claude"]  # claude has system_file=None
        content = _generate_system_prompt(cfg)
        assert content is None

    def test_returns_none_for_empty_parts(self, test_project):
        shutil.rmtree(test_project / ".vaultspec" / "rules" / "system")
        cfg = _types.TOOL_CONFIGS["gemini"]
        content = _generate_system_prompt(cfg)
        assert content is None

    def test_order_frontmatter_respected(self, test_project):
        """Files with lower order appear before files with higher/default order."""
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        # workflow has order: 20 (should appear first among shared)
        (test_project / ".vaultspec" / "rules" / "system" / "workflow.md").write_text(
            "---\norder: 20\n---\n\n# WORKFLOW", encoding="utf-8"
        )
        # operations has no order (defaults to 50, should appear after workflow)
        (test_project / ".vaultspec" / "rules" / "system" / "operations.md").write_text(
            "---\n---\n\n# OPERATIONS", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["gemini"]
        content = _generate_system_prompt(cfg)
        assert content is not None
        workflow_pos = content.index("# WORKFLOW")
        operations_pos = content.index("# OPERATIONS")
        assert workflow_pos < operations_pos

    def test_pipeline_config_excluded(self, test_project):
        """Parts with pipeline: config are excluded from system prompt."""
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "---\npipeline: config\n---\n\n# FRAMEWORK CONFIG", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["gemini"]
        content = _generate_system_prompt(cfg)
        assert content is not None
        assert "# BASE" in content
        assert "# FRAMEWORK CONFIG" not in content

    def test_includes_skill_listing(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )
        deploy_dir = (
            test_project / ".vaultspec" / "rules" / "skills" / "vaultspec-deploy"
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
    def test_generates_for_tool_without_system_file(self, test_project):
        """Claude (rules_dir but no system_file) gets behavioral rules."""
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE MANDATES", encoding="utf-8"
        )
        (test_project / ".vaultspec" / "rules" / "system" / "operations.md").write_text(
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

    def test_excludes_tool_specific_parts(self, test_project):
        """Behavioral rules exclude tool-specific parts."""
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        (
            test_project / ".vaultspec" / "rules" / "system" / "gemini-tools.md"
        ).write_text("---\ntool: gemini\n---\n\n# GEMINI ONLY", encoding="utf-8")
        (test_project / ".vaultspec" / "rules" / "system" / "shared.md").write_text(
            "---\n---\n\n# SHARED", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_system_rules(cfg)
        assert content is not None
        assert "# BASE" in content
        assert "# SHARED" in content
        assert "# GEMINI ONLY" not in content

    def test_excludes_pipeline_config(self, test_project):
        """Behavioral rules exclude pipeline: config parts."""
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "---\npipeline: config\n---\n\n# CONFIG ONLY", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_system_rules(cfg)
        assert content is not None
        assert "# BASE" in content
        assert "# CONFIG ONLY" not in content

    def test_returns_none_without_rules_dir(self, test_project):
        """ToolConfig with no rules_dir returns None."""
        cfg = ToolConfig(name="test", rules_dir=None, skills_dir=None)
        content = _generate_system_rules(cfg)
        assert content is None

    def test_returns_none_when_system_rule_emission_disabled(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        assert _generate_system_rules(_types.TOOL_CONFIGS["antigravity"]) is None
        assert _generate_system_rules(_types.TOOL_CONFIGS["codex"]) is None

    def test_returns_none_for_empty_parts(self, test_project):
        shutil.rmtree(test_project / ".vaultspec" / "rules" / "system")
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_system_rules(cfg)
        assert content is None

    def test_order_frontmatter_respected(self, test_project):
        """Order frontmatter controls assembly order in rules too."""
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        (test_project / ".vaultspec" / "rules" / "system" / "workflow.md").write_text(
            "---\norder: 20\n---\n\n# WORKFLOW", encoding="utf-8"
        )
        (test_project / ".vaultspec" / "rules" / "system" / "operations.md").write_text(
            "---\n---\n\n# OPERATIONS", encoding="utf-8"
        )
        cfg = _types.TOOL_CONFIGS["claude"]
        content = _generate_system_rules(cfg)
        assert content is not None
        workflow_pos = content.index("# WORKFLOW")
        operations_pos = content.index("# OPERATIONS")
        assert workflow_pos < operations_pos
