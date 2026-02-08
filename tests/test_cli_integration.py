"""Integration tests for cli.py sync workflows.

Every test uses the `cli_workspace` fixture which creates a fully isolated
temp workspace and redirects all CLI globals via init_paths().  These tests
never touch the real repo.
"""

from __future__ import annotations

import argparse
import pathlib

import pytest

import cli as cli_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(**kwargs) -> argparse.Namespace:
    """Quick argparse.Namespace builder with sensible defaults."""
    defaults = {"dry_run": False, "prune": False, "force": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _write_rule(workspace: pathlib.Path, name: str, body: str, *, custom: bool = False) -> None:
    subdir = "rules-custom" if custom else "rules"
    path = workspace / ".rules" / subdir / name
    path.write_text(body, encoding="utf-8")


def _write_agent(workspace: pathlib.Path, name: str, description: str, tier: str, body: str) -> None:
    content = cli_mod.build_file({"description": description, "tier": tier}, body)
    (workspace / ".rules" / "agents" / name).write_text(content, encoding="utf-8")


def _write_skill(workspace: pathlib.Path, name: str, description: str, body: str) -> None:
    content = cli_mod.build_file({"description": description}, body)
    (workspace / ".rules" / "skills" / f"{name}.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Rules sync
# ---------------------------------------------------------------------------


class TestRulesSync:
    def test_sync_creates_destinations(self, cli_workspace):
        _write_rule(cli_workspace, "my-rule.md", "# My Rule\n\nContent here.\n")
        cli_mod.rules_sync(_make_args())

        for dest_dir in (".claude", ".gemini", ".agent"):
            dest = cli_workspace / dest_dir / "rules" / "my-rule.md"
            assert dest.exists(), f"Missing {dest}"

    def test_destination_has_correct_frontmatter(self, cli_workspace):
        _write_rule(cli_workspace, "test-rule.md", "# Test\n")
        cli_mod.rules_sync(_make_args())

        # Claude should have name + trigger
        content = (cli_workspace / ".claude" / "rules" / "test-rule.md").read_text(encoding="utf-8")
        meta, body = cli_mod.parse_frontmatter(content)
        assert meta["name"] == "test-rule"
        assert meta["trigger"] == "always_on"

    def test_custom_overrides_builtin(self, cli_workspace):
        _write_rule(cli_workspace, "shared.md", "Built-in version.\n")
        _write_rule(cli_workspace, "shared.md", "Custom version.\n", custom=True)
        cli_mod.rules_sync(_make_args())

        content = (cli_workspace / ".claude" / "rules" / "shared.md").read_text(encoding="utf-8")
        assert "Custom version." in content

    def test_prune_removes_orphans(self, cli_workspace):
        _write_rule(cli_workspace, "keep.md", "Keep me.\n")
        cli_mod.rules_sync(_make_args())

        # Verify it exists
        orphan = cli_workspace / ".claude" / "rules" / "keep.md"
        assert orphan.exists()

        # Remove from source, sync with prune
        (cli_workspace / ".rules" / "rules" / "keep.md").unlink()
        cli_mod.rules_sync(_make_args(prune=True))
        assert not orphan.exists()

    def test_agent_rules_no_name_field(self, cli_workspace):
        _write_rule(cli_workspace, "no-name.md", "Agent rule body.\n")
        cli_mod.rules_sync(_make_args())

        content = (cli_workspace / ".agent" / "rules" / "no-name.md").read_text(encoding="utf-8")
        meta, _ = cli_mod.parse_frontmatter(content)
        assert "name" not in meta
        assert meta["trigger"] == "always_on"


# ---------------------------------------------------------------------------
# Agents sync
# ---------------------------------------------------------------------------


class TestAgentsSync:
    def test_sync_creates_agent_files(self, cli_workspace):
        _write_agent(cli_workspace, "my-agent.md", "Test agent", "MEDIUM", "# Persona\n")
        cli_mod.agents_sync(_make_args())

        # Claude and Gemini should have agent files
        for tool in ("claude", "gemini"):
            dest = cli_workspace / f".{tool}" / "agents" / "my-agent.md"
            assert dest.exists(), f"Missing {dest}"

    def test_all_tiers_resolve(self, cli_workspace):
        tiers = {
            "low-agent.md": ("LOW", "claude-haiku-4-5", "gemini-2.5-flash"),
            "med-agent.md": ("MEDIUM", "claude-sonnet-4-5", "gemini-3-flash-preview"),
            "high-agent.md": ("HIGH", "claude-opus-4-6", "gemini-3-pro-preview"),
        }
        for name, (tier, _, _) in tiers.items():
            _write_agent(cli_workspace, name, f"{tier} agent", tier, "body\n")

        cli_mod.agents_sync(_make_args())

        for name, (_, claude_model, gemini_model) in tiers.items():
            claude_content = (cli_workspace / ".claude" / "agents" / name).read_text(encoding="utf-8")
            gemini_content = (cli_workspace / ".gemini" / "agents" / name).read_text(encoding="utf-8")

            claude_fm, _ = cli_mod.parse_frontmatter(claude_content)
            gemini_fm, _ = cli_mod.parse_frontmatter(gemini_content)

            assert claude_fm["model"] == claude_model, f"{name} claude model mismatch"
            assert gemini_fm["model"] == gemini_model, f"{name} gemini model mismatch"

    def test_agent_not_synced_to_dot_agent(self, cli_workspace):
        _write_agent(cli_workspace, "solo.md", "Solo", "LOW", "body\n")
        cli_mod.agents_sync(_make_args())

        # .agent has agents_dir=None so nothing should appear
        agent_dest = cli_workspace / ".agent" / "agents" / "solo.md"
        assert not agent_dest.exists()


# ---------------------------------------------------------------------------
# Skills sync
# ---------------------------------------------------------------------------


class TestSkillsSync:
    def test_sync_creates_skill_subdirs(self, cli_workspace):
        _write_skill(cli_workspace, "task-test", "A test skill", "# Instructions\n")
        cli_mod.skills_sync(_make_args())

        for dest_dir in (".claude", ".gemini", ".agent"):
            dest = cli_workspace / dest_dir / "skills" / "task-test" / "SKILL.md"
            assert dest.exists(), f"Missing {dest}"

    def test_skill_has_correct_frontmatter(self, cli_workspace):
        _write_skill(cli_workspace, "task-check", "Check skill", "# Check\n")
        cli_mod.skills_sync(_make_args())

        content = (cli_workspace / ".claude" / "skills" / "task-check" / "SKILL.md").read_text(encoding="utf-8")
        meta, body = cli_mod.parse_frontmatter(content)
        assert meta["name"] == "task-check"
        assert meta["description"] == "Check skill"

    def test_protected_skills_not_pruned(self, cli_workspace):
        # Create a protected skill dir manually
        protected = cli_workspace / ".claude" / "skills" / "fd"
        protected.mkdir(parents=True, exist_ok=True)
        (protected / "SKILL.md").write_text("# FD skill\n", encoding="utf-8")

        cli_mod.skills_sync(_make_args(prune=True))

        # Protected skill must survive prune
        assert (protected / "SKILL.md").exists()

    def test_prune_removes_orphan_task_skills(self, cli_workspace):
        _write_skill(cli_workspace, "task-orphan", "Orphan", "body\n")
        cli_mod.skills_sync(_make_args())

        orphan = cli_workspace / ".claude" / "skills" / "task-orphan" / "SKILL.md"
        assert orphan.exists()

        # Remove source, prune
        (cli_workspace / ".rules" / "skills" / "task-orphan.md").unlink()
        cli_mod.skills_sync(_make_args(prune=True))
        assert not orphan.exists()


# ---------------------------------------------------------------------------
# Config sync
# ---------------------------------------------------------------------------


class TestConfigSync:
    def test_generates_config_files(self, cli_workspace):
        # Need at least one rule for refs
        _write_rule(cli_workspace, "my-rule.md", "# Rule\n")
        cli_mod.rules_sync(_make_args())
        cli_mod.config_sync(_make_args())

        for path in (
            cli_workspace / ".claude" / "CLAUDE.md",
            cli_workspace / ".gemini" / "GEMINI.md",
        ):
            assert path.exists(), f"Missing {path}"
            content = path.read_text(encoding="utf-8")
            assert content.startswith(cli_mod.CONFIG_HEADER)
            assert "# Test Mission" in content
            assert "@" in content  # Has rule refs

    def test_safety_guard_blocks_custom_file(self, cli_workspace):
        # Write a non-CLI-managed file
        custom = cli_workspace / ".claude" / "CLAUDE.md"
        custom.write_text("# My hand-written config\n", encoding="utf-8")

        cli_mod.config_sync(_make_args())

        # Should NOT be overwritten
        content = custom.read_text(encoding="utf-8")
        assert "hand-written" in content

    def test_force_overwrites_custom_file(self, cli_workspace):
        custom = cli_workspace / ".claude" / "CLAUDE.md"
        custom.write_text("# My hand-written config\n", encoding="utf-8")

        cli_mod.config_sync(_make_args(force=True))

        content = custom.read_text(encoding="utf-8")
        assert content.startswith(cli_mod.CONFIG_HEADER)
        assert "hand-written" not in content

    def test_idempotent_second_sync(self, cli_workspace):
        cli_mod.config_sync(_make_args())
        # Second sync without force should succeed (file is CLI-managed)
        cli_mod.config_sync(_make_args())

        content = (cli_workspace / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        assert content.startswith(cli_mod.CONFIG_HEADER)

    def test_config_contains_rule_refs(self, cli_workspace):
        _write_rule(cli_workspace, "alpha.md", "alpha\n")
        _write_rule(cli_workspace, "beta.md", "beta\n")
        cli_mod.rules_sync(_make_args())
        cli_mod.config_sync(_make_args())

        content = (cli_workspace / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "@rules/alpha.md" in content
        assert "@rules/beta.md" in content


# ---------------------------------------------------------------------------
# sync-all
# ---------------------------------------------------------------------------


class TestSyncAll:
    def test_sync_all_ordering(self, cli_workspace):
        """Rules must sync before config so config refs match synced rules."""
        _write_rule(cli_workspace, "first.md", "# First\n")
        _write_agent(cli_workspace, "bot.md", "Bot", "LOW", "body\n")
        _write_skill(cli_workspace, "task-do", "Do skill", "body\n")

        # Simulate sync-all order: rules -> agents -> skills -> config
        cli_mod.rules_sync(_make_args())
        cli_mod.agents_sync(_make_args())
        cli_mod.skills_sync(_make_args())
        cli_mod.config_sync(_make_args())

        config = (cli_workspace / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "@rules/first.md" in config


# ---------------------------------------------------------------------------
# collect_rules edge cases
# ---------------------------------------------------------------------------


class TestCollectRules:
    def test_empty_when_dirs_missing(self, cli_workspace):
        # Remove source dirs
        import shutil
        shutil.rmtree(cli_workspace / ".rules" / "rules")
        shutil.rmtree(cli_workspace / ".rules" / "rules-custom")

        result = cli_mod.collect_rules()
        assert result == {}

    def test_collects_from_both_dirs(self, cli_workspace):
        _write_rule(cli_workspace, "builtin.md", "built-in\n")
        _write_rule(cli_workspace, "custom.md", "custom\n", custom=True)

        result = cli_mod.collect_rules()
        assert "builtin.md" in result
        assert "custom.md" in result


# ---------------------------------------------------------------------------
# _collect_rule_refs
# ---------------------------------------------------------------------------


class TestCollectRuleRefs:
    def test_returns_sorted_relative_paths(self, cli_workspace):
        # Create rules in destination
        rules_dir = cli_workspace / ".claude" / "rules"
        (rules_dir / "beta.md").write_text("b\n", encoding="utf-8")
        (rules_dir / "alpha.md").write_text("a\n", encoding="utf-8")

        cfg = cli_mod.TOOL_CONFIGS["claude"]
        refs = cli_mod._collect_rule_refs(cfg)
        assert refs == ["rules/alpha.md", "rules/beta.md"]

    def test_empty_when_no_rules(self, cli_workspace):
        cfg = cli_mod.TOOL_CONFIGS["claude"]
        # Clear rules dir
        for f in (cli_workspace / ".claude" / "rules").glob("*.md"):
            f.unlink()
        refs = cli_mod._collect_rule_refs(cfg)
        assert refs == []
