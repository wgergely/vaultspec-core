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
    _generate_codex_native_config_body,
    _generate_config_body,
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


def _cfg(tool: Tool) -> ToolConfig:
    return _types.get_context().tool_configs[tool]


class TestCollectRules:
    def test_builtin_and_custom(self, synthetic_project):
        """Both .builtin.md and plain .md files are collected from rules/rules/."""
        (
            synthetic_project / ".vaultspec" / "rules" / "rules" / "a.builtin.md"
        ).write_text("---\nname: a\n---\n\nBuilt-in A", encoding="utf-8")
        (synthetic_project / ".vaultspec" / "rules" / "rules" / "b.md").write_text(
            "---\nname: b\n---\n\nCustom B", encoding="utf-8"
        )
        sources = collect_rules()
        assert "a.builtin.md" in sources
        assert "b.md" in sources

    def test_empty_dirs(self, synthetic_project):
        # Clear any pre-existing rules so dirs exist but are empty
        rules_dir = synthetic_project / ".vaultspec" / "rules" / "rules"
        for f in rules_dir.glob("*.md"):
            f.unlink()
        sources = collect_rules()
        assert sources == {}

    def test_missing_dirs(self, synthetic_project):
        shutil.rmtree(synthetic_project / ".vaultspec" / "rules")
        sources = collect_rules()
        assert sources == {}

    def test_builtin_suffix_detected(self, synthetic_project):
        """Builtin rules use .builtin.md suffix; custom rules use plain .md."""
        (
            synthetic_project / ".vaultspec" / "rules" / "rules" / "core.builtin.md"
        ).write_text("---\nname: core\n---\n\nBuilt-in content", encoding="utf-8")
        (synthetic_project / ".vaultspec" / "rules" / "rules" / "custom.md").write_text(
            "---\nname: custom\n---\n\nCustom content", encoding="utf-8"
        )
        sources = collect_rules()
        assert "core.builtin.md" in sources
        assert "custom.md" in sources


class TestCollectSkills:
    def test_collects_all_skill_directories(self, synthetic_project):
        """Any directory with a SKILL.md is collected, regardless of naming."""
        deploy_dir = (
            synthetic_project / ".vaultspec" / "rules" / "skills" / "vaultspec-deploy"
        )
        deploy_dir.mkdir(parents=True, exist_ok=True)
        (deploy_dir / "SKILL.md").write_text(
            "---\ndescription: Deploy\n---\n\n# Deploy", encoding="utf-8"
        )
        helper_dir = (
            synthetic_project / ".vaultspec" / "rules" / "skills" / "utility-helper"
        )
        helper_dir.mkdir(parents=True, exist_ok=True)
        (helper_dir / "SKILL.md").write_text(
            "---\ndescription: Helper\n---\n\n# Helper", encoding="utf-8"
        )
        skills = collect_skills()
        assert "vaultspec-deploy" in skills
        assert "utility-helper" in skills

    def test_empty_skills_dir(self, synthetic_project):
        # Clear any pre-existing skills so the dir is empty
        import shutil as _shutil

        skills_dir = synthetic_project / ".vaultspec" / "rules" / "skills"
        if skills_dir.exists():
            _shutil.rmtree(skills_dir)
            skills_dir.mkdir()
        assert collect_skills() == {}


class TestCollectSystemParts:
    def test_with_tool_filter(self, synthetic_project):
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base prompt", encoding="utf-8"
        )
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "gemini-extra.md"
        ).write_text("---\ntool: gemini\n---\n\n# Gemini only", encoding="utf-8")
        parts = collect_system_parts()
        assert "base" in parts
        assert "gemini-extra" in parts
        _path, meta, _body = parts["gemini-extra"]
        assert meta["tool"] == "gemini"

    def test_missing_dir(self, synthetic_project):
        shutil.rmtree(synthetic_project / ".vaultspec" / "rules" / "system")
        assert collect_system_parts() == {}


class TestTransformRule:
    def test_claude_includes_name(self, synthetic_project):
        out = transform_rule(Tool.CLAUDE, "my-rule.md", {}, "Body text")
        meta, body = parse_frontmatter(out)
        assert meta["name"] == "my-rule"
        assert meta["trigger"] == "always_on"
        assert "Body text" in body

    def test_gemini_includes_name(self, synthetic_project):
        out = transform_rule(Tool.GEMINI, "rule.md", {}, "Content")
        meta, _body = parse_frontmatter(out)
        assert meta["name"] == "rule"


class TestTransformSkill:
    def test_extracts_description(self, synthetic_project):
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
    def test_skill_listing_format(self, synthetic_project):
        deploy_dir = (
            synthetic_project / ".vaultspec" / "rules" / "skills" / "vaultspec-deploy"
        )
        deploy_dir.mkdir(parents=True, exist_ok=True)
        (deploy_dir / "SKILL.md").write_text(
            "---\ndescription: Deploy things\n---\n\nbody",
            encoding="utf-8",
        )
        listing = _collect_skill_listing()
        assert "## Vaultspec Skills" in listing
        assert "**vaultspec-deploy**" in listing
        assert "Deploy things" in listing

    def test_skill_listing_empty(self, synthetic_project):
        # Clear any pre-existing skills so listing is empty
        import shutil as _shutil

        skills_dir = synthetic_project / ".vaultspec" / "rules" / "skills"
        if skills_dir.exists():
            _shutil.rmtree(skills_dir)
            skills_dir.mkdir()
        listing = _collect_skill_listing()
        assert listing == ""


class TestGenerateConfig:
    def test_returns_none_without_rules(self, synthetic_project):
        """Config body is None when no synced rules exist."""
        # Clear any pre-existing synced rules from the real corpus
        rules_dir = synthetic_project / ".claude" / "rules"
        if rules_dir.exists():
            for f in rules_dir.glob("*.md"):
                f.unlink()
        content = _generate_config_body(_cfg(Tool.CLAUDE))
        assert content is None

    def test_includes_rule_references(self, synthetic_project):
        """Config body includes @rule references when synced rules exist."""
        (synthetic_project / ".claude" / "rules" / "my-rule.md").write_text(
            "rule content", encoding="utf-8"
        )
        content = _generate_config_body(_cfg(Tool.CLAUDE))
        assert content is not None
        assert "@.claude/rules/my-rule.md" in content

    def test_antigravity_uses_workspace_rules_for_root_gemini(self, synthetic_project):
        (synthetic_project / ".agents" / "rules").mkdir(parents=True, exist_ok=True)
        (synthetic_project / ".agents" / "rules" / "workspace-rule.md").write_text(
            "rule content", encoding="utf-8"
        )
        content = _generate_config_body(_cfg(Tool.ANTIGRAVITY))
        assert content is not None
        assert "@.agents/rules/workspace-rule.md" in content

    def test_codex_native_config_uses_explicit_frontmatter(self, synthetic_project):
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "codex-cfg.md"
        ).write_text(
            "---\n"
            "pipeline: config\n"
            "codex_model: gpt-5-codex\n"
            "codex_approval_policy: on-request\n"
            "codex_project_root_markers:\n"
            "  - .git\n"
            "  - pyproject.toml\n"
            "---\n\nInternal",
            encoding="utf-8",
        )
        content = _generate_codex_native_config_body()
        assert content is not None
        assert 'model = "gpt-5-codex"' in content
        assert 'approval_policy = "on-request"' in content
        assert 'project_root_markers = [".git", "pyproject.toml"]' in content

    def test_codex_native_config_later_file_overrides(self, synthetic_project):
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "01-codex.md"
        ).write_text(
            "---\npipeline: config\ncodex_sandbox_mode: read-only\n---\n\nFirst",
            encoding="utf-8",
        )
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "02-codex.md"
        ).write_text(
            "---\npipeline: config\ncodex_sandbox_mode: workspace-write\n---\n\nSecond",
            encoding="utf-8",
        )
        content = _generate_codex_native_config_body()
        assert content is not None
        assert 'sandbox_mode = "workspace-write"' in content

    def test_codex_native_config_supports_reasoning_and_service_tier(
        self, synthetic_project
    ):
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "codex-cfg.md"
        ).write_text(
            "---\n"
            "pipeline: config\n"
            "codex_model_reasoning_effort: high\n"
            "codex_model_reasoning_summary: auto\n"
            "codex_model_supports_reasoning_summaries: true\n"
            "codex_model_verbosity: low\n"
            "codex_service_tier: flex\n"
            "---\n\nInternal",
            encoding="utf-8",
        )
        content = _generate_codex_native_config_body()
        assert content is not None
        assert 'model_reasoning_effort = "high"' in content
        assert 'model_reasoning_summary = "auto"' in content
        assert "model_supports_reasoning_summaries = true" in content
        assert 'model_verbosity = "low"' in content
        assert 'service_tier = "flex"' in content


class TestCodexNegativeCoverage:
    """Verify Codex does NOT generate artifacts outside its native model."""

    def test_codex_has_no_system_file(self, synthetic_project):
        """Codex ToolConfig must not declare a system_file."""
        assert _cfg(Tool.CODEX).system_file is None

    def test_codex_has_no_agents_dir(self, synthetic_project):
        """Codex agent definitions use TOML, not a synced agents_dir."""
        assert _cfg(Tool.CODEX).agents_dir is None

    def test_codex_emit_system_rule_enabled(self, synthetic_project):
        """Codex emits behavioral rules via the system rule fallback."""
        assert _cfg(Tool.CODEX).emit_system_rule is True

    def test_system_prompt_returns_none_for_codex(self, synthetic_project):
        """Codex has no dedicated system_file, so system prompt is None."""
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base system prompt", encoding="utf-8"
        )
        assert _generate_system_prompt(_cfg(Tool.CODEX)) is None

    def test_system_rules_generated_for_codex(self, synthetic_project):
        """Codex gets system rules via emit_system_rule=True."""
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base system prompt", encoding="utf-8"
        )
        result = _generate_system_rules(_cfg(Tool.CODEX))
        assert result is not None
        assert "Base system prompt" in result

    def test_codex_native_config_returns_none_without_codex_keys(
        self, synthetic_project
    ):
        """If no codex_* frontmatter keys exist, native config returns None."""
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "some-part.md"
        ).write_text(
            "---\npipeline: config\nname: some-part\n---\n\nInternal", encoding="utf-8"
        )
        assert _generate_codex_native_config_body() is None


class TestGenerateSystemPrompt:
    def test_assembly_order(self, synthetic_project):
        # tool-specific parts come first
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "gemini-tools.md"
        ).write_text("---\ntool: gemini\n---\n\n# GEMINI TOOLS", encoding="utf-8")
        # shared parts come after, sorted by order
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "01-core.md"
        ).write_text("---\norder: 1\n---\n\n# CORE CONTENT", encoding="utf-8")
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "90-custom.md"
        ).write_text("---\norder: 90\n---\n\n# CUSTOM CONTENT", encoding="utf-8")

        content = _generate_system_prompt(_cfg(Tool.GEMINI))
        assert content is not None

        # Verify ordering: tool-specific -> shared (by order)
        tool_pos = content.index("# GEMINI TOOLS")
        core_pos = content.index("# CORE CONTENT")
        custom_pos = content.index("# CUSTOM CONTENT")
        assert tool_pos < core_pos < custom_pos

    def test_shared_parts_only(self, synthetic_project):
        (synthetic_project / ".vaultspec" / "rules" / "system" / "extra.md").write_text(
            "---\n---\n\n# Extra", encoding="utf-8"
        )
        content = _generate_system_prompt(_cfg(Tool.GEMINI))
        assert content is not None
        assert "# Extra" in content

    def test_multiple_tool_specific_parts(self, synthetic_project):
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "01-core.md"
        ).write_text("---\norder: 1\n---\n\n# Core", encoding="utf-8")
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "gemini-a.md"
        ).write_text("---\ntool: gemini\n---\n\n# Gemini A", encoding="utf-8")
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "gemini-b.md"
        ).write_text("---\ntool: gemini\n---\n\n# Gemini B", encoding="utf-8")
        content = _generate_system_prompt(_cfg(Tool.GEMINI))
        assert content is not None
        assert "# Gemini A" in content
        assert "# Gemini B" in content

    def test_returns_none_for_no_system_file(self, synthetic_project):
        content = _generate_system_prompt(
            _cfg(Tool.CLAUDE)
        )  # claude has system_file=None
        assert content is None

    def test_returns_none_for_empty_parts(self, synthetic_project):
        shutil.rmtree(synthetic_project / ".vaultspec" / "rules" / "system")
        content = _generate_system_prompt(_cfg(Tool.GEMINI))
        assert content is None

    def test_order_frontmatter_respected(self, synthetic_project):
        """Files with lower order appear before files with higher/default order."""
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        # workflow has order: 20 (should appear first among shared)
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "workflow.md"
        ).write_text("---\norder: 20\n---\n\n# WORKFLOW", encoding="utf-8")
        # operations has no order (defaults to 50, should appear after workflow)
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "operations.md"
        ).write_text("---\n---\n\n# OPERATIONS", encoding="utf-8")
        content = _generate_system_prompt(_cfg(Tool.GEMINI))
        assert content is not None
        workflow_pos = content.index("# WORKFLOW")
        operations_pos = content.index("# OPERATIONS")
        assert workflow_pos < operations_pos

    def test_pipeline_config_excluded(self, synthetic_project):
        """Parts with pipeline: config are excluded from system prompt."""
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "framework.md"
        ).write_text(
            "---\npipeline: config\n---\n\n# FRAMEWORK CONFIG", encoding="utf-8"
        )
        content = _generate_system_prompt(_cfg(Tool.GEMINI))
        assert content is not None
        assert "# BASE" in content
        assert "# FRAMEWORK CONFIG" not in content

    def test_includes_skill_listing(self, synthetic_project):
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )
        deploy_dir = (
            synthetic_project / ".vaultspec" / "rules" / "skills" / "vaultspec-deploy"
        )
        deploy_dir.mkdir(parents=True, exist_ok=True)
        (deploy_dir / "SKILL.md").write_text(
            "---\ndescription: Deploy service\n---\n\n# Deploy",
            encoding="utf-8",
        )
        content = _generate_system_prompt(_cfg(Tool.GEMINI))
        assert content is not None
        assert "## Vaultspec Skills" in content
        assert "**vaultspec-deploy**" in content


class TestGenerateSystemRules:
    def test_generates_for_tool_without_system_file(self, synthetic_project):
        """Claude (rules_dir but no system_file) gets behavioral rules."""
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE MANDATES", encoding="utf-8"
        )
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "operations.md"
        ).write_text("---\n---\n\n# OPERATIONS", encoding="utf-8")
        content = _generate_system_rules(_cfg(Tool.CLAUDE))
        assert content is not None
        assert "# BASE MANDATES" in content
        assert "# OPERATIONS" in content
        meta, _body = parse_frontmatter(content.replace(CONFIG_HEADER + "\n", ""))
        assert meta["name"] == "vaultspec-system"
        assert meta["trigger"] == "always_on"

    def test_excludes_tool_specific_parts(self, synthetic_project):
        """Behavioral rules exclude tool-specific parts."""
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "gemini-tools.md"
        ).write_text("---\ntool: gemini\n---\n\n# GEMINI ONLY", encoding="utf-8")
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "shared.md"
        ).write_text("---\n---\n\n# SHARED", encoding="utf-8")
        content = _generate_system_rules(_cfg(Tool.CLAUDE))
        assert content is not None
        assert "# BASE" in content
        assert "# SHARED" in content
        assert "# GEMINI ONLY" not in content

    def test_excludes_pipeline_config(self, synthetic_project):
        """Behavioral rules exclude pipeline: config parts."""
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "framework.md"
        ).write_text("---\npipeline: config\n---\n\n# CONFIG ONLY", encoding="utf-8")
        content = _generate_system_rules(_cfg(Tool.CLAUDE))
        assert content is not None
        assert "# BASE" in content
        assert "# CONFIG ONLY" not in content

    def test_returns_none_without_rules_dir(self, synthetic_project):
        """ToolConfig with no rules_dir returns None."""
        cfg = ToolConfig(name="test", rules_dir=None, skills_dir=None)
        content = _generate_system_rules(cfg)
        assert content is None

    def test_returns_none_when_system_rule_emission_disabled(self, synthetic_project):
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        # Antigravity has emit_system_rule=False
        assert _generate_system_rules(_cfg(Tool.ANTIGRAVITY)) is None

    def test_returns_none_for_empty_parts(self, synthetic_project):
        shutil.rmtree(synthetic_project / ".vaultspec" / "rules" / "system")
        content = _generate_system_rules(_cfg(Tool.CLAUDE))
        assert content is None

    def test_order_frontmatter_respected(self, synthetic_project):
        """Order frontmatter controls assembly order in rules too."""
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# BASE", encoding="utf-8"
        )
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "workflow.md"
        ).write_text("---\norder: 20\n---\n\n# WORKFLOW", encoding="utf-8")
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "operations.md"
        ).write_text("---\n---\n\n# OPERATIONS", encoding="utf-8")
        content = _generate_system_rules(_cfg(Tool.CLAUDE))
        assert content is not None
        workflow_pos = content.index("# WORKFLOW")
        operations_pos = content.index("# OPERATIONS")
        assert workflow_pos < operations_pos
