"""Comprehensive test suite for .vaultspec/scripts/cli.py sync engine.

Tests frontmatter utilities, file operations, collect/transform functions,
sync operations, assembly, and end-to-end sync cycles.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit]

# Scripts path added by conftest.py; import cli directly
import cli  # noqa: E402

TEST_PROJECT = Path(__file__).resolve().parent.parent.parent.parent / "test-project"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cleanup_test_project(root: Path) -> None:
    """Remove transient artifacts, preserving .vault/ and README."""
    for item in root.iterdir():
        if item.name in (".vault", "README.md", ".gitignore"):
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


def _setup_rules_dir(root: Path) -> None:
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


def _make_ns(**kwargs) -> argparse.Namespace:
    """Build an argparse.Namespace with sensible defaults for sync commands."""
    defaults = {"prune": False, "dry_run": False, "force": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# Patch PROVIDERS so tests never depend on actual model resolution
_MOCK_PROVIDERS: dict[str, dict[str, str]] = {
    "claude": {"LOW": "claude-haiku", "MEDIUM": "claude-sonnet", "HIGH": "claude-opus"},
    "gemini": {"LOW": "gemini-flash", "MEDIUM": "gemini-pro", "HIGH": "gemini-ultra"},
}


def _mock_resolve_model(tool: str, tier: str) -> str | None:
    provider = _MOCK_PROVIDERS.get(tool)
    if provider is None:
        return None
    return provider.get(tier.upper())


@pytest.fixture(autouse=True)
def _isolate_cli():
    """Reset cli globals to test-project before every test."""
    cli.init_paths(TEST_PROJECT)
    _setup_rules_dir(TEST_PROJECT)
    yield
    _cleanup_test_project(TEST_PROJECT)


# =========================================================================
# Frontmatter utilities
# =========================================================================


class TestParseFrontmatter:
    def test_valid_yaml(self):
        content = "---\nname: hello\ntrigger: always_on\n---\n\n# Body"
        meta, body = cli.parse_frontmatter(content)
        assert meta["name"] == "hello"
        assert meta["trigger"] == "always_on"
        assert body.strip() == "# Body"

    def test_no_frontmatter(self):
        content = "# Just a heading\n\nSome text."
        meta, body = cli.parse_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_empty_frontmatter(self):
        """Empty frontmatter (no chars between ---) doesn't match the regex,
        so the whole content is returned as-is."""
        content = "---\n---\n\nBody content"
        meta, body = cli.parse_frontmatter(content)
        assert meta == {}
        # Regex requires at least one char between delimiters, so body == original
        assert "Body content" in body

    def test_whitespace_only_frontmatter(self):
        """Frontmatter with only whitespace parses to empty dict."""
        content = "---\n \n---\n\nBody content"
        meta, body = cli.parse_frontmatter(content)
        assert meta == {}
        assert body.strip() == "Body content"

    def test_leading_whitespace_stripped(self):
        content = "\n\n---\nname: test\n---\n\nbody"
        meta, body = cli.parse_frontmatter(content)
        assert meta["name"] == "test"
        assert body.strip() == "body"

    def test_multiline_body_preserved(self):
        content = "---\nk: v\n---\n\nLine 1\nLine 2\nLine 3"
        _meta, body = cli.parse_frontmatter(content)
        assert "Line 1\nLine 2\nLine 3" in body


class TestBuildFile:
    def test_round_trip(self):
        fm = {"name": "test-rule", "trigger": "always_on"}
        body = "# My Rule\n\nDo the thing."
        output = cli.build_file(fm, body)
        assert output.startswith("---\n")
        assert "---\n\n" in output
        meta2, body2 = cli.parse_frontmatter(output)
        assert meta2["name"] == "test-rule"
        assert "Do the thing." in body2

    def test_empty_body(self):
        fm = {"name": "empty"}
        output = cli.build_file(fm, "")
        assert output.endswith("---\n\n")
        meta2, body2 = cli.parse_frontmatter(output)
        assert meta2["name"] == "empty"
        assert body2.strip() == ""


# =========================================================================
# File operations
# =========================================================================


class TestAtomicWrite:
    def test_creates_new_file(self):
        p = TEST_PROJECT / "new.md"
        cli.atomic_write(p, "hello world")
        assert p.read_text(encoding="utf-8") == "hello world"

    def test_overwrites_existing(self):
        p = TEST_PROJECT / "existing.md"
        p.write_text("old content", encoding="utf-8")
        cli.atomic_write(p, "new content")
        assert p.read_text(encoding="utf-8") == "new content"

    def test_no_temp_file_left(self):
        p = TEST_PROJECT / "clean.md"
        cli.atomic_write(p, "data")
        assert not (TEST_PROJECT / "clean.md.tmp").exists()


class TestIsCliManaged:
    def test_managed_file(self):
        p = TEST_PROJECT / "CLAUDE.md"
        p.write_text(f"{cli.CONFIG_HEADER}\nrest of content", encoding="utf-8")
        assert cli._is_cli_managed(p) is True

    def test_custom_file(self):
        p = TEST_PROJECT / "CLAUDE.md"
        p.write_text("# My custom config\n\nHand-written.", encoding="utf-8")
        assert cli._is_cli_managed(p) is False

    def test_nonexistent_file(self):
        p = TEST_PROJECT / "nope.md"
        assert cli._is_cli_managed(p) is False

    def test_empty_file(self):
        p = TEST_PROJECT / "empty.md"
        p.write_text("", encoding="utf-8")
        assert cli._is_cli_managed(p) is False


# =========================================================================
# Collect functions
# =========================================================================


class TestCollectRules:
    def test_builtin_and_custom(self):
        (TEST_PROJECT / ".vaultspec" / "rules" / "a.md").write_text(
            "---\nname: a\n---\n\nBuilt-in A", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules-custom" / "b.md").write_text(
            "---\nname: b\n---\n\nCustom B", encoding="utf-8"
        )
        sources = cli.collect_rules()
        assert "a.md" in sources
        assert "b.md" in sources

    def test_empty_dirs(self):
        # dirs exist but are empty
        sources = cli.collect_rules()
        assert sources == {}

    def test_missing_dirs(self):
        shutil.rmtree(TEST_PROJECT / ".vaultspec" / "rules")
        shutil.rmtree(TEST_PROJECT / ".vaultspec" / "rules-custom")
        sources = cli.collect_rules()
        assert sources == {}

    def test_custom_overrides_builtin(self):
        """When both dirs have same-named file, custom wins (appears later)."""
        (TEST_PROJECT / ".vaultspec" / "rules" / "dup.md").write_text(
            "---\nname: dup\n---\n\nBuilt-in", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules-custom" / "dup.md").write_text(
            "---\nname: dup\n---\n\nCustom override", encoding="utf-8"
        )
        sources = cli.collect_rules()
        assert "dup.md" in sources
        _path, _meta, body = sources["dup.md"]
        assert "Custom override" in body


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
        (TEST_PROJECT / ".vaultspec" / "skills" / "spec-deploy.md").write_text(
            "---\ndescription: Deploy\n---\n\n# Deploy", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "skills" / "utility-helper.md").write_text(
            "---\ndescription: Helper\n---\n\n# Helper", encoding="utf-8"
        )
        skills = cli.collect_skills()
        assert "spec-deploy" in skills
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


# =========================================================================
# Transform functions
# =========================================================================


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
    @patch.object(cli, "resolve_model", side_effect=_mock_resolve_model)
    def test_valid_tier(self, _mock_rm):
        result = cli.transform_agent(
            "claude", "coder.md", {"description": "A coder", "tier": "HIGH"}, "Body"
        )
        assert result is not None
        meta, body = cli.parse_frontmatter(result)
        assert meta["model"] == "claude-opus"
        assert meta["name"] == "coder"
        assert "Body" in body

    @patch.object(cli, "resolve_model", return_value=None)
    def test_missing_model_returns_none(self, _mock_rm):
        result = cli.transform_agent(
            "claude", "agent.md", {"description": "x", "tier": "HIGH"}, "Body"
        )
        assert result is None

    def test_missing_tier_returns_none(self):
        result = cli.transform_agent("claude", "agent.md", {"description": "x"}, "Body")
        assert result is None


class TestTransformSkill:
    def test_extracts_description(self):
        out = cli.transform_skill(
            "claude", "spec-deploy", {"description": "Deploy things"}, "# Deploy"
        )
        meta, body = cli.parse_frontmatter(out)
        assert meta["description"] == "Deploy things"
        assert meta["name"] == "spec-deploy"
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
        (TEST_PROJECT / ".vaultspec" / "skills" / "spec-deploy.md").write_text(
            "---\ndescription: Deploy things\n---\n\nbody",
            encoding="utf-8",
        )
        listing = cli._collect_skill_listing()
        assert "## Available Skills" in listing
        assert "**spec-deploy**" in listing
        assert "Deploy things" in listing

    def test_skill_listing_empty(self):
        listing = cli._collect_skill_listing()
        assert listing == ""


# =========================================================================
# Sync operations
# =========================================================================


class TestSyncFiles:
    def _make_sources(
        self, root: Path, names: list[str]
    ) -> dict[str, tuple[Path, dict, str]]:
        sources = {}
        for name in names:
            p = root / name
            p.write_text(f"---\nname: {name}\n---\n\n# {name}", encoding="utf-8")
            sources[name] = (p, {"name": name}, f"# {name}")
        return sources

    def test_adds_new_files(self):
        dest = TEST_PROJECT / "dest"
        dest.mkdir()
        sources = self._make_sources(TEST_PROJECT, ["a.md", "b.md"])
        result = cli.sync_files(
            sources=sources,
            dest_dir=dest,
            transform_fn=lambda _t, n, m, b: cli.transform_rule("claude", n, m, b),
            dest_path_fn=lambda d, n: d / n,
            prune=False,
            dry_run=False,
            label="test",
        )
        assert result.added == 2
        assert (dest / "a.md").exists()
        assert (dest / "b.md").exists()

    def test_updates_existing(self):
        dest = TEST_PROJECT / "dest"
        dest.mkdir()
        (dest / "a.md").write_text("old", encoding="utf-8")
        sources = self._make_sources(TEST_PROJECT, ["a.md"])
        result = cli.sync_files(
            sources=sources,
            dest_dir=dest,
            transform_fn=lambda _t, n, m, b: cli.transform_rule("claude", n, m, b),
            dest_path_fn=lambda d, n: d / n,
            prune=False,
            dry_run=False,
            label="test",
        )
        assert result.updated == 1
        assert "old" not in (dest / "a.md").read_text(encoding="utf-8")

    def test_prune_removes_stale(self):
        dest = TEST_PROJECT / "dest"
        dest.mkdir()
        (dest / "stale.md").write_text("old", encoding="utf-8")
        sources = self._make_sources(TEST_PROJECT, ["a.md"])
        result = cli.sync_files(
            sources=sources,
            dest_dir=dest,
            transform_fn=lambda _t, n, m, b: cli.transform_rule("claude", n, m, b),
            dest_path_fn=lambda d, n: d / n,
            prune=True,
            dry_run=False,
            label="test",
        )
        assert result.pruned == 1
        assert not (dest / "stale.md").exists()

    def test_no_prune_preserves_stale(self):
        dest = TEST_PROJECT / "dest"
        dest.mkdir()
        (dest / "stale.md").write_text("old", encoding="utf-8")
        sources = self._make_sources(TEST_PROJECT, ["a.md"])
        result = cli.sync_files(
            sources=sources,
            dest_dir=dest,
            transform_fn=lambda _t, n, m, b: cli.transform_rule("claude", n, m, b),
            dest_path_fn=lambda d, n: d / n,
            prune=False,
            dry_run=False,
            label="test",
        )
        assert result.pruned == 0
        assert (dest / "stale.md").exists()

    def test_dry_run_doesnt_write(self):
        dest = TEST_PROJECT / "dest"
        dest.mkdir()
        sources = self._make_sources(TEST_PROJECT, ["a.md"])
        result = cli.sync_files(
            sources=sources,
            dest_dir=dest,
            transform_fn=lambda _t, n, m, b: cli.transform_rule("claude", n, m, b),
            dest_path_fn=lambda d, n: d / n,
            prune=False,
            dry_run=True,
            label="test",
        )
        assert result.added == 1
        assert not (dest / "a.md").exists()

    def test_transform_returning_none_skips(self):
        dest = TEST_PROJECT / "dest"
        dest.mkdir()
        sources = self._make_sources(TEST_PROJECT, ["a.md"])
        result = cli.sync_files(
            sources=sources,
            dest_dir=dest,
            transform_fn=lambda _t, _n, _m, _b: None,
            dest_path_fn=lambda d, n: d / n,
            prune=False,
            dry_run=False,
            label="test",
        )
        assert result.skipped == 1
        assert result.added == 0


class TestSyncSkills:
    def _make_skill_sources(
        self, root: Path, names: list[str]
    ) -> dict[str, tuple[Path, dict, str]]:
        sources = {}
        for name in names:
            p = root / f"{name}.md"
            p.write_text(f"---\ndescription: {name}\n---\n\n# {name}", encoding="utf-8")
            sources[name] = (p, {"description": name}, f"# {name}")
        return sources

    def test_creates_skill_dirs(self):
        skills_dir = TEST_PROJECT / "skills"
        skills_dir.mkdir()
        sources = self._make_skill_sources(TEST_PROJECT, ["spec-deploy"])
        result = cli.sync_skills(
            sources=sources,
            skills_dir=skills_dir,
            transform_fn=lambda _t, n, m, b: cli.transform_skill("claude", n, m, b),
            prune=False,
            dry_run=False,
            label="test",
        )
        assert result.added == 1
        assert (skills_dir / "spec-deploy" / "SKILL.md").exists()

    def test_prune_respects_protected(self):
        skills_dir = TEST_PROJECT / "skills"
        # Create a protected skill directory
        (skills_dir / "fd").mkdir(parents=True)
        (skills_dir / "fd" / "SKILL.md").write_text("protected", encoding="utf-8")
        # Create a non-protected spec- skill directory to prune
        (skills_dir / "spec-old").mkdir(parents=True)
        (skills_dir / "spec-old" / "SKILL.md").write_text("stale", encoding="utf-8")

        sources = self._make_skill_sources(TEST_PROJECT, ["spec-deploy"])
        result = cli.sync_skills(
            sources=sources,
            skills_dir=skills_dir,
            transform_fn=lambda _t, n, m, b: cli.transform_skill("claude", n, m, b),
            prune=True,
            dry_run=False,
            label="test",
        )
        # Protected skill kept
        assert (skills_dir / "fd" / "SKILL.md").exists()
        # Stale spec- skill pruned
        assert result.pruned == 1
        assert not (skills_dir / "spec-old" / "SKILL.md").exists()

    def test_prune_skips_non_task_dirs(self):
        skills_dir = TEST_PROJECT / "skills"
        (skills_dir / "my-custom-skill").mkdir(parents=True)
        (skills_dir / "my-custom-skill" / "SKILL.md").write_text(
            "custom", encoding="utf-8"
        )

        result = cli.sync_skills(
            sources={},
            skills_dir=skills_dir,
            transform_fn=lambda _t, n, m, b: cli.transform_skill("claude", n, m, b),
            prune=True,
            dry_run=False,
            label="test",
        )
        assert result.pruned == 0
        assert (skills_dir / "my-custom-skill" / "SKILL.md").exists()


class TestSystemSync:
    def test_generates_from_parts(self):
        (TEST_PROJECT / ".vaultspec" / "system" / "base.md").write_text(
            "---\n---\n\n# Base system prompt", encoding="utf-8"
        )
        args = _make_ns()
        cli.system_sync(args)
        # Only gemini has system_file
        system_file = TEST_PROJECT / ".gemini" / "SYSTEM.md"
        assert system_file.exists()
        content = system_file.read_text(encoding="utf-8")
        assert content.startswith(cli.CONFIG_HEADER)
        assert "# Base system prompt" in content

    def test_skips_custom_file(self):
        (TEST_PROJECT / ".vaultspec" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )
        system_file = TEST_PROJECT / ".gemini" / "SYSTEM.md"
        system_file.write_text("# My custom system prompt", encoding="utf-8")
        args = _make_ns()
        cli.system_sync(args)
        content = system_file.read_text(encoding="utf-8")
        assert content == "# My custom system prompt"

    def test_force_overwrites_custom(self):
        (TEST_PROJECT / ".vaultspec" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )
        system_file = TEST_PROJECT / ".gemini" / "SYSTEM.md"
        system_file.write_text("# Custom", encoding="utf-8")
        args = _make_ns(force=True)
        cli.system_sync(args)
        content = system_file.read_text(encoding="utf-8")
        assert content.startswith(cli.CONFIG_HEADER)
        assert "# Base" in content


class TestConfigSync:
    def test_generates_from_internal_and_custom(self):
        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "Internal instructions here", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "PROJECT.md").write_text(
            "Custom user content", encoding="utf-8"
        )
        args = _make_ns()
        cli.config_sync(args)
        config_file = TEST_PROJECT / ".claude" / "CLAUDE.md"
        assert config_file.exists()
        content = config_file.read_text(encoding="utf-8")
        assert cli.CONFIG_HEADER in content
        assert "Custom user content" in content

    def test_generates_with_internal_only(self):
        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "Internal only", encoding="utf-8"
        )
        args = _make_ns()
        cli.config_sync(args)
        config_file = TEST_PROJECT / ".claude" / "CLAUDE.md"
        assert config_file.exists()

    def test_skips_when_no_internal(self):
        args = _make_ns()
        cli.config_sync(args)
        config_file = TEST_PROJECT / ".claude" / "CLAUDE.md"
        assert not config_file.exists()

    def test_skips_custom_dest_without_force(self):
        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "Internal", encoding="utf-8"
        )
        config_file = TEST_PROJECT / ".claude" / "CLAUDE.md"
        config_file.write_text("# Hand-written config", encoding="utf-8")
        args = _make_ns()
        cli.config_sync(args)
        content = config_file.read_text(encoding="utf-8")
        assert content == "# Hand-written config"

    def test_force_overwrites_custom_dest(self):
        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "Internal", encoding="utf-8"
        )
        config_file = TEST_PROJECT / ".claude" / "CLAUDE.md"
        config_file.write_text("# Hand-written", encoding="utf-8")
        args = _make_ns(force=True)
        cli.config_sync(args)
        content = config_file.read_text(encoding="utf-8")
        assert content.startswith(cli.CONFIG_HEADER)


# =========================================================================
# Assembly / _generate_config / _generate_system_prompt
# =========================================================================


class TestGenerateConfig:
    def test_internal_and_custom(self):
        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "Internal body", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "PROJECT.md").write_text(
            "Custom body", encoding="utf-8"
        )
        cfg = cli.TOOL_CONFIGS["claude"]
        content = cli._generate_config(cfg)
        assert content is not None
        assert cli.CONFIG_HEADER in content
        assert "Custom body" in content

    def test_internal_only(self):
        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
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
        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
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
        (TEST_PROJECT / ".vaultspec" / "skills" / "spec-deploy.md").write_text(
            "---\ndescription: Deploy service\n---\n\n# Deploy",
            encoding="utf-8",
        )
        cfg = cli.TOOL_CONFIGS["gemini"]
        content = cli._generate_system_prompt(cfg)
        assert content is not None
        assert "## Available Skills" in content
        assert "**spec-deploy**" in content


# =========================================================================
# End-to-end cycles
# =========================================================================


class TestEndToEnd:
    @patch.object(cli, "resolve_model", side_effect=_mock_resolve_model)
    def test_full_sync_cycle(self, _mock_rm):
        """Create sources -> sync -> verify destinations."""
        # Set up source files
        (TEST_PROJECT / ".vaultspec" / "rules" / "no-swear.md").write_text(
            "---\nname: no-swear\n---\n\nDo not swear.", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "agents" / "reviewer.md").write_text(
            "---\ndescription: Reviews code\ntier: MEDIUM\n---\n\n# Reviewer",
            encoding="utf-8",
        )
        (TEST_PROJECT / ".vaultspec" / "skills" / "spec-lint.md").write_text(
            "---\ndescription: Run linter\n---\n\n# Lint", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "Be helpful.", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "system" / "base.md").write_text(
            "---\n---\n\n# You are an assistant.", encoding="utf-8"
        )

        # Sync all
        args = _make_ns()
        cli.rules_sync(args)
        cli.agents_sync(args)
        cli.skills_sync(args)
        cli.config_sync(args)
        cli.system_sync(args)

        # Verify rules
        assert (TEST_PROJECT / ".claude" / "rules" / "no-swear.md").exists()
        assert (TEST_PROJECT / ".gemini" / "rules" / "no-swear.md").exists()
        assert (TEST_PROJECT / ".agent" / "rules" / "no-swear.md").exists()

        # Verify agents
        assert (TEST_PROJECT / ".claude" / "agents" / "reviewer.md").exists()
        assert (TEST_PROJECT / ".gemini" / "agents" / "reviewer.md").exists()

        # Verify skills
        assert (TEST_PROJECT / ".claude" / "skills" / "spec-lint" / "SKILL.md").exists()

        # Verify config
        assert (TEST_PROJECT / ".claude" / "CLAUDE.md").exists()

        # Verify system
        assert (TEST_PROJECT / ".gemini" / "SYSTEM.md").exists()

    @patch.object(cli, "resolve_model", side_effect=_mock_resolve_model)
    def test_modify_resync_cycle(self, _mock_rm):
        """Sync -> modify source -> sync -> verify update."""
        rule_src = TEST_PROJECT / ".vaultspec" / "rules" / "rule1.md"
        rule_src.write_text("---\nname: rule1\n---\n\nOriginal body.", encoding="utf-8")
        args = _make_ns()
        cli.rules_sync(args)

        dest = TEST_PROJECT / ".claude" / "rules" / "rule1.md"
        assert dest.exists()
        content_v1 = dest.read_text(encoding="utf-8")
        assert "Original body" in content_v1

        # Modify source
        rule_src.write_text("---\nname: rule1\n---\n\nUpdated body.", encoding="utf-8")
        cli.rules_sync(args)

        content_v2 = dest.read_text(encoding="utf-8")
        assert "Updated body" in content_v2

    @patch.object(cli, "resolve_model", side_effect=_mock_resolve_model)
    def test_prune_cycle(self, _mock_rm):
        """Sync -> delete source -> sync --prune -> verify deletion."""
        rule_src = TEST_PROJECT / ".vaultspec" / "rules" / "ephemeral.md"
        rule_src.write_text("---\nname: ephemeral\n---\n\nGone soon.", encoding="utf-8")
        args = _make_ns()
        cli.rules_sync(args)

        dest = TEST_PROJECT / ".claude" / "rules" / "ephemeral.md"
        assert dest.exists()

        # Delete source and re-sync with prune
        rule_src.unlink()
        args_prune = _make_ns(prune=True)
        cli.rules_sync(args_prune)
        assert not dest.exists()

    @patch.object(cli, "resolve_model", side_effect=_mock_resolve_model)
    def test_force_overwrite_cycle(self, _mock_rm):
        """Create custom dest -> sync (skip) -> sync --force (overwrite)."""
        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "Internal content", encoding="utf-8"
        )

        config_file = TEST_PROJECT / ".claude" / "CLAUDE.md"
        config_file.write_text("# My hand-written config", encoding="utf-8")

        # Normal sync should skip custom config
        args = _make_ns()
        cli.config_sync(args)
        content = config_file.read_text(encoding="utf-8")
        assert content == "# My hand-written config"

        # Force sync overwrites
        args_force = _make_ns(force=True)
        cli.config_sync(args_force)
        content = config_file.read_text(encoding="utf-8")
        assert content.startswith(cli.CONFIG_HEADER)
        assert "# My hand-written config" not in content


# =========================================================================
# Incremental & multi-pass integration
# =========================================================================


class TestIncrementalRules:
    """Multi-pass rule sync: add, modify, remove, prune across iterations."""

    @patch.object(cli, "resolve_model", side_effect=_mock_resolve_model)
    def test_add_modify_remove_loop(self, _mock_rm):
        """Full lifecycle: add/sync/modify/prune."""
        rules_dir = TEST_PROJECT / ".vaultspec" / "rules"
        args = _make_ns()
        args_prune = _make_ns(prune=True)

        # --- Pass 1: add 3 rules ---
        for name in ["alpha", "beta", "gamma"]:
            (rules_dir / f"{name}.md").write_text(
                f"---\nname: {name}\n---\n\n{name} v1", encoding="utf-8"
            )
        cli.rules_sync(args)

        for tool_dir in [".claude", ".gemini", ".agent"]:
            for name in ["alpha", "beta", "gamma"]:
                assert (TEST_PROJECT / tool_dir / "rules" / f"{name}.md").exists()

        # --- Pass 2: modify beta, add delta ---
        (rules_dir / "beta.md").write_text(
            "---\nname: beta\n---\n\nbeta v2 modified", encoding="utf-8"
        )
        (rules_dir / "delta.md").write_text(
            "---\nname: delta\n---\n\ndelta v1", encoding="utf-8"
        )
        cli.rules_sync(args)

        claude_beta = (TEST_PROJECT / ".claude" / "rules" / "beta.md").read_text(
            encoding="utf-8"
        )
        assert "beta v2 modified" in claude_beta
        assert (TEST_PROJECT / ".claude" / "rules" / "delta.md").exists()

        # --- Pass 3: remove alpha + gamma, prune ---
        (rules_dir / "alpha.md").unlink()
        (rules_dir / "gamma.md").unlink()
        cli.rules_sync(args_prune)
        assert not (TEST_PROJECT / ".claude" / "rules" / "alpha.md").exists()
        assert not (TEST_PROJECT / ".claude" / "rules" / "gamma.md").exists()
        assert not (TEST_PROJECT / ".gemini" / "rules" / "alpha.md").exists()
        assert not (TEST_PROJECT / ".agent" / "rules" / "gamma.md").exists()
        # beta and delta survive across all destinations
        for tool_dir in [".claude", ".gemini", ".agent"]:
            assert (TEST_PROJECT / tool_dir / "rules" / "beta.md").exists()
            assert (TEST_PROJECT / tool_dir / "rules" / "delta.md").exists()

    @patch.object(cli, "resolve_model", side_effect=_mock_resolve_model)
    def test_idempotent_resync(self, _mock_rm):
        """Syncing twice with no changes keeps files identical."""
        (TEST_PROJECT / ".vaultspec" / "rules" / "stable.md").write_text(
            "---\nname: stable\n---\n\nstable content", encoding="utf-8"
        )
        args = _make_ns()
        cli.rules_sync(args)
        content_v1 = (TEST_PROJECT / ".claude" / "rules" / "stable.md").read_text(
            encoding="utf-8"
        )
        cli.rules_sync(args)
        content_v2 = (TEST_PROJECT / ".claude" / "rules" / "stable.md").read_text(
            encoding="utf-8"
        )
        assert content_v1 == content_v2

    @patch.object(cli, "resolve_model", side_effect=_mock_resolve_model)
    def test_cross_destination_consistency(self, _mock_rm):
        """All tool destinations get the same body content after sync."""
        (TEST_PROJECT / ".vaultspec" / "rules" / "shared.md").write_text(
            "---\nname: shared\n---\n\nshared content here", encoding="utf-8"
        )
        cli.rules_sync(_make_ns())

        bodies = {}
        for tool_dir in [".claude", ".gemini", ".agent"]:
            p = TEST_PROJECT / tool_dir / "rules" / "shared.md"
            assert p.exists(), f"Missing in {tool_dir}"
            _meta, body = cli.parse_frontmatter(p.read_text(encoding="utf-8"))
            bodies[tool_dir] = body.strip()

        # All destinations have the same body content
        assert bodies[".claude"] == bodies[".gemini"] == bodies[".agent"]

    @patch.object(cli, "resolve_model", side_effect=_mock_resolve_model)
    def test_five_pass_churn(self, _mock_rm):
        """Simulate 5 sync passes with different mutations each time."""
        rules_dir = TEST_PROJECT / ".vaultspec" / "rules"
        args = _make_ns()
        args_prune = _make_ns(prune=True)

        # Pass 1: add a, b
        for n in ["a", "b"]:
            (rules_dir / f"{n}.md").write_text(
                f"---\nname: {n}\n---\n\n{n}", encoding="utf-8"
            )
        cli.rules_sync(args)

        # Pass 2: add c, modify a
        (rules_dir / "c.md").write_text("---\nname: c\n---\n\nc", encoding="utf-8")
        (rules_dir / "a.md").write_text("---\nname: a\n---\n\na-mod", encoding="utf-8")
        cli.rules_sync(args)

        # Pass 3: remove b, add d
        (rules_dir / "b.md").unlink()
        (rules_dir / "d.md").write_text("---\nname: d\n---\n\nd", encoding="utf-8")
        cli.rules_sync(args_prune)

        # Pass 4: remove c, modify d
        (rules_dir / "c.md").unlink()
        (rules_dir / "d.md").write_text("---\nname: d\n---\n\nd-mod", encoding="utf-8")
        cli.rules_sync(args_prune)

        # Pass 5: no changes, just sync
        cli.rules_sync(args)

        # Final state: a (modified), d (modified) survive; b, c pruned
        for tool_dir in [".claude", ".gemini", ".agent"]:
            assert (TEST_PROJECT / tool_dir / "rules" / "a.md").exists()
            assert (TEST_PROJECT / tool_dir / "rules" / "d.md").exists()
            assert not (TEST_PROJECT / tool_dir / "rules" / "b.md").exists()
            assert not (TEST_PROJECT / tool_dir / "rules" / "c.md").exists()

        a_content = (TEST_PROJECT / ".claude" / "rules" / "a.md").read_text(
            encoding="utf-8"
        )
        assert "a-mod" in a_content
        d_content = (TEST_PROJECT / ".claude" / "rules" / "d.md").read_text(
            encoding="utf-8"
        )
        assert "d-mod" in d_content


class TestIncrementalAgents:
    """Agent add/modify/remove across sync passes."""

    @patch.object(cli, "resolve_model", side_effect=_mock_resolve_model)
    def test_agent_lifecycle(self, _mock_rm):
        agents_dir = TEST_PROJECT / ".vaultspec" / "agents"
        args = _make_ns()
        args_prune = _make_ns(prune=True)

        # Add agent
        (agents_dir / "coder.md").write_text(
            "---\ndescription: Writes code\ntier: HIGH\n---\n\n# Coder v1",
            encoding="utf-8",
        )
        cli.agents_sync(args)
        assert (TEST_PROJECT / ".claude" / "agents" / "coder.md").exists()
        assert (TEST_PROJECT / ".gemini" / "agents" / "coder.md").exists()

        # Modify agent
        (agents_dir / "coder.md").write_text(
            "---\ndescription: Writes code well\ntier: HIGH\n---\n\n# Coder v2",
            encoding="utf-8",
        )
        cli.agents_sync(args)
        content = (TEST_PROJECT / ".claude" / "agents" / "coder.md").read_text(
            encoding="utf-8"
        )
        assert "Coder v2" in content

        # Remove agent + prune
        (agents_dir / "coder.md").unlink()
        cli.agents_sync(args_prune)
        assert not (TEST_PROJECT / ".claude" / "agents" / "coder.md").exists()
        assert not (TEST_PROJECT / ".gemini" / "agents" / "coder.md").exists()

    @patch.object(cli, "resolve_model", side_effect=_mock_resolve_model)
    def test_agent_tier_change(self, _mock_rm):
        """Changing an agent's tier changes the resolved model in output."""
        agents_dir = TEST_PROJECT / ".vaultspec" / "agents"
        args = _make_ns()

        (agents_dir / "flex.md").write_text(
            "---\ndescription: Flexible\ntier: LOW\n---\n\n# Flex",
            encoding="utf-8",
        )
        cli.agents_sync(args)
        c1 = (TEST_PROJECT / ".claude" / "agents" / "flex.md").read_text(
            encoding="utf-8"
        )
        assert "claude-haiku" in c1

        (agents_dir / "flex.md").write_text(
            "---\ndescription: Flexible\ntier: HIGH\n---\n\n# Flex upgraded",
            encoding="utf-8",
        )
        cli.agents_sync(args)
        c2 = (TEST_PROJECT / ".claude" / "agents" / "flex.md").read_text(
            encoding="utf-8"
        )
        assert "claude-opus" in c2
        assert "Flex upgraded" in c2


class TestIncrementalSkills:
    """Skill add/modify/remove across sync passes."""

    @patch.object(cli, "resolve_model", side_effect=_mock_resolve_model)
    def test_skill_lifecycle(self, _mock_rm):
        skills_dir = TEST_PROJECT / ".vaultspec" / "skills"
        args = _make_ns()
        args_prune = _make_ns(prune=True)

        # Add skill
        (skills_dir / "spec-deploy.md").write_text(
            "---\ndescription: Deploy service\n---\n\n# Deploy v1",
            encoding="utf-8",
        )
        cli.skills_sync(args)
        assert (
            TEST_PROJECT / ".claude" / "skills" / "spec-deploy" / "SKILL.md"
        ).exists()

        # Modify skill
        (skills_dir / "spec-deploy.md").write_text(
            "---\ndescription: Deploy service v2\n---\n\n# Deploy updated",
            encoding="utf-8",
        )
        cli.skills_sync(args)
        content = (
            TEST_PROJECT / ".claude" / "skills" / "spec-deploy" / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert "Deploy updated" in content

        # Add second skill, remove first, prune
        (skills_dir / "spec-test.md").write_text(
            "---\ndescription: Run tests\n---\n\n# Test",
            encoding="utf-8",
        )
        (skills_dir / "spec-deploy.md").unlink()
        cli.skills_sync(args_prune)
        assert not (TEST_PROJECT / ".claude" / "skills" / "spec-deploy").exists()
        assert (TEST_PROJECT / ".claude" / "skills" / "spec-test" / "SKILL.md").exists()


class TestIncrementalSystem:
    """System prompt incremental changes across sync passes."""

    def test_system_add_modify_cycle(self):
        system_dir = TEST_PROJECT / ".vaultspec" / "system"
        args = _make_ns(force=True)

        # Pass 1: single base part
        (system_dir / "base.md").write_text("---\n---\n\n# Base v1", encoding="utf-8")
        cli.system_sync(args)
        content_v1 = (TEST_PROJECT / ".gemini" / "SYSTEM.md").read_text(
            encoding="utf-8"
        )
        assert "# Base v1" in content_v1
        assert "# Extra" not in content_v1

        # Pass 2: add a shared part
        (system_dir / "extra.md").write_text(
            "---\n---\n\n# Extra section", encoding="utf-8"
        )
        cli.system_sync(args)
        content_v2 = (TEST_PROJECT / ".gemini" / "SYSTEM.md").read_text(
            encoding="utf-8"
        )
        assert "# Base v1" in content_v2
        assert "# Extra section" in content_v2

        # Pass 3: modify base
        (system_dir / "base.md").write_text(
            "---\n---\n\n# Base v2 updated", encoding="utf-8"
        )
        cli.system_sync(args)
        content_v3 = (TEST_PROJECT / ".gemini" / "SYSTEM.md").read_text(
            encoding="utf-8"
        )
        assert "# Base v2 updated" in content_v3
        assert "# Base v1" not in content_v3
        assert "# Extra section" in content_v3

    def test_system_idempotent(self):
        """Syncing system twice with no changes produces identical output."""
        (TEST_PROJECT / ".vaultspec" / "system" / "base.md").write_text(
            "---\n---\n\n# Stable base", encoding="utf-8"
        )
        args = _make_ns(force=True)
        cli.system_sync(args)
        content_v1 = (TEST_PROJECT / ".gemini" / "SYSTEM.md").read_text(
            encoding="utf-8"
        )
        cli.system_sync(args)
        content_v2 = (TEST_PROJECT / ".gemini" / "SYSTEM.md").read_text(
            encoding="utf-8"
        )
        assert content_v1 == content_v2


class TestIncrementalConfig:
    """Config sync responds to FRAMEWORK.md / PROJECT.md changes."""

    def test_framework_content_change_propagates(self):
        args = _make_ns(force=True)

        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "v1 framework", encoding="utf-8"
        )
        cli.config_sync(args)
        c1 = (TEST_PROJECT / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "v1 framework" in c1

        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "v2 framework", encoding="utf-8"
        )
        cli.config_sync(args)
        c2 = (TEST_PROJECT / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "v2 framework" in c2
        assert "v1 framework" not in c2

    def test_project_content_change_propagates(self):
        args = _make_ns(force=True)

        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "framework", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "PROJECT.md").write_text(
            "project v1", encoding="utf-8"
        )
        cli.config_sync(args)
        c1 = (TEST_PROJECT / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "project v1" in c1

        (TEST_PROJECT / ".vaultspec" / "PROJECT.md").write_text(
            "project v2", encoding="utf-8"
        )
        cli.config_sync(args)
        c2 = (TEST_PROJECT / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "project v2" in c2
        assert "project v1" not in c2


class TestMixedOperations:
    """Cross-resource-type operations in a single integration flow."""

    @patch.object(cli, "resolve_model", side_effect=_mock_resolve_model)
    def test_full_mixed_lifecycle(self, _mock_rm):
        """Add rules+agents+skills, sync, modify+remove some, resync."""
        rules_dir = TEST_PROJECT / ".vaultspec" / "rules"
        agents_dir = TEST_PROJECT / ".vaultspec" / "agents"
        skills_dir = TEST_PROJECT / ".vaultspec" / "skills"
        system_dir = TEST_PROJECT / ".vaultspec" / "system"
        args = _make_ns()
        args_prune = _make_ns(prune=True)

        # --- Setup: add everything ---
        (rules_dir / "r1.md").write_text(
            "---\nname: r1\n---\n\nRule 1", encoding="utf-8"
        )
        (rules_dir / "r2.md").write_text(
            "---\nname: r2\n---\n\nRule 2", encoding="utf-8"
        )
        (agents_dir / "builder.md").write_text(
            "---\ndescription: Builds\ntier: MEDIUM\n---\n\n# Builder",
            encoding="utf-8",
        )
        (skills_dir / "spec-build.md").write_text(
            "---\ndescription: Build it\n---\n\n# Build", encoding="utf-8"
        )
        (system_dir / "base.md").write_text(
            "---\n---\n\n# System base", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "Framework content", encoding="utf-8"
        )

        # Sync all
        cli.rules_sync(args)
        cli.agents_sync(args)
        cli.skills_sync(args)
        cli.config_sync(args)
        cli.system_sync(args)

        # Verify initial state
        assert (TEST_PROJECT / ".claude" / "rules" / "r1.md").exists()
        assert (TEST_PROJECT / ".claude" / "rules" / "r2.md").exists()
        assert (TEST_PROJECT / ".claude" / "agents" / "builder.md").exists()
        assert (
            TEST_PROJECT / ".claude" / "skills" / "spec-build" / "SKILL.md"
        ).exists()
        assert (TEST_PROJECT / ".claude" / "CLAUDE.md").exists()
        assert (TEST_PROJECT / ".gemini" / "SYSTEM.md").exists()

        # --- Mutate: modify r1, remove r2, add r3, modify agent, remove skill ---
        (rules_dir / "r1.md").write_text(
            "---\nname: r1\n---\n\nRule 1 MODIFIED", encoding="utf-8"
        )
        (rules_dir / "r2.md").unlink()
        (rules_dir / "r3.md").write_text(
            "---\nname: r3\n---\n\nRule 3 new", encoding="utf-8"
        )
        (agents_dir / "builder.md").write_text(
            "---\ndescription: Builds fast\ntier: HIGH\n---\n\n# Builder v2",
            encoding="utf-8",
        )
        (skills_dir / "spec-build.md").unlink()

        # Re-sync with prune
        cli.rules_sync(args_prune)
        cli.agents_sync(args_prune)
        cli.skills_sync(args_prune)
        cli.config_sync(args)
        cli.system_sync(args)

        # Verify mutated state
        r1_content = (TEST_PROJECT / ".claude" / "rules" / "r1.md").read_text(
            encoding="utf-8"
        )
        assert "Rule 1 MODIFIED" in r1_content
        assert not (TEST_PROJECT / ".claude" / "rules" / "r2.md").exists()
        assert (TEST_PROJECT / ".claude" / "rules" / "r3.md").exists()

        builder = (TEST_PROJECT / ".claude" / "agents" / "builder.md").read_text(
            encoding="utf-8"
        )
        assert "Builder v2" in builder

        assert not (TEST_PROJECT / ".claude" / "skills" / "spec-build").exists()

        # System prompt should reflect updated agent listing
        system = (TEST_PROJECT / ".gemini" / "SYSTEM.md").read_text(encoding="utf-8")
        assert "Builds fast" in system


# =========================================================================
# init_paths
# =========================================================================


class TestInitPaths:
    def test_sets_globals(self):
        cli.init_paths(TEST_PROJECT)
        assert TEST_PROJECT == cli.ROOT_DIR
        assert TEST_PROJECT / ".vaultspec" / "rules" == cli.RULES_SRC_DIR
        assert TEST_PROJECT / ".vaultspec" / "rules-custom" == cli.RULES_CUSTOM_DIR
        assert TEST_PROJECT / ".vaultspec" / "agents" == cli.AGENTS_SRC_DIR
        assert TEST_PROJECT / ".vaultspec" / "skills" == cli.SKILLS_SRC_DIR
        assert TEST_PROJECT / ".vaultspec" / "system" == cli.SYSTEM_SRC_DIR
        assert TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md" == cli.FRAMEWORK_CONFIG_SRC
        assert TEST_PROJECT / ".vaultspec" / "PROJECT.md" == cli.PROJECT_CONFIG_SRC

    def test_tool_configs_populated(self):
        cli.init_paths(TEST_PROJECT)
        assert "claude" in cli.TOOL_CONFIGS
        assert "gemini" in cli.TOOL_CONFIGS
        assert "antigravity" in cli.TOOL_CONFIGS
        assert "agents" in cli.TOOL_CONFIGS
        assert (
            cli.TOOL_CONFIGS["claude"].rules_dir == TEST_PROJECT / ".claude" / "rules"
        )


# =========================================================================
# SyncResult / print_summary
# =========================================================================


class TestSyncResult:
    def test_default_values(self):
        r = cli.SyncResult()
        assert r.added == 0
        assert r.updated == 0
        assert r.skipped == 0
        assert r.pruned == 0
        assert r.errors == []

    def test_print_summary_no_changes(self, capsys):
        cli.print_summary("Test", cli.SyncResult())
        captured = capsys.readouterr()
        assert "no changes" in captured.out

    def test_print_summary_with_counts(self, capsys):
        r = cli.SyncResult(added=2, updated=1, pruned=3)
        cli.print_summary("Rules", r)
        captured = capsys.readouterr()
        assert "2 added" in captured.out
        assert "1 updated" in captured.out
        assert "3 pruned" in captured.out
