"""Sync operation tests for the CLI sync engine.

Covers: sync_files, rules_sync, skills_sync, system_sync, config_sync.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from vaultspec_core.core.enums import Tool

from ...core import (
    agents_sync,
    config_sync,
    rules_sync,
    skills_sync,
    sync_files,
    system_sync,
    transform_rule,
)

pytestmark = [pytest.mark.unit]


class TestSyncFiles:
    """Tests for the generic sync_files utility."""

    def _make_sources(self, root: Path, names: list[str]):
        sources = {}
        for name in names:
            p = root / name
            p.write_text(f"body {name}", encoding="utf-8")
            sources[name] = (p, {}, f"body {name}")
        return sources

    def test_adds_new_files(self, test_project):
        dest = test_project / "dest"
        dest.mkdir()
        sources = self._make_sources(test_project, ["a.md", "b.md"])
        result = sync_files(
            sources=sources,
            dest_dir=dest,
            transform_fn=lambda _t, n, m, b: transform_rule(Tool.CLAUDE, n, m, b),
            dest_path_fn=lambda d, n: d / n,
            prune=False,
            dry_run=False,
            label="test",
        )
        assert result.added == 2
        assert (dest / "a.md").exists()
        assert (dest / "b.md").exists()

    def test_updates_existing_files(self, test_project):
        dest = test_project / "dest"
        dest.mkdir()
        (dest / "a.md").write_text("old", encoding="utf-8")
        sources = self._make_sources(test_project, ["a.md"])
        result = sync_files(
            sources=sources,
            dest_dir=dest,
            transform_fn=lambda _t, n, m, b: transform_rule(Tool.CLAUDE, n, m, b),
            dest_path_fn=lambda d, n: d / n,
            prune=False,
            dry_run=False,
            label="test",
        )
        assert result.updated == 1
        assert (dest / "a.md").read_text(encoding="utf-8") != "old"

    def test_skips_unchanged_files(self, test_project):
        dest = test_project / "dest"
        dest.mkdir()
        sources = self._make_sources(test_project, ["a.md"])
        # First sync to create
        sync_files(
            sources=sources,
            dest_dir=dest,
            transform_fn=lambda _t, n, m, b: transform_rule(Tool.CLAUDE, n, m, b),
            dest_path_fn=lambda d, n: d / n,
            prune=False,
            dry_run=False,
            label="test",
        )
        # Second sync with no changes
        result = sync_files(
            sources=sources,
            dest_dir=dest,
            transform_fn=lambda _t, n, m, b: transform_rule(Tool.CLAUDE, n, m, b),
            dest_path_fn=lambda d, n: d / n,
            prune=False,
            dry_run=False,
            label="test",
        )
        assert result.skipped == 1
        assert result.added == 0
        assert result.updated == 0

    def test_prune_removes_stale(self, test_project):
        dest = test_project / "dest"
        dest.mkdir()
        (dest / "stale.md").write_text("old", encoding="utf-8")
        sources = self._make_sources(test_project, ["a.md"])
        result = sync_files(
            sources=sources,
            dest_dir=dest,
            transform_fn=lambda _t, n, m, b: transform_rule(Tool.CLAUDE, n, m, b),
            dest_path_fn=lambda d, n: d / n,
            prune=True,
            dry_run=False,
            label="test",
        )
        assert result.pruned == 1
        assert not (dest / "stale.md").exists()


class TestSyncSkills:
    """Tests for skills_sync."""

    def _make_skill_sources(self, root: Path, names: list[str]):
        skills_dir = root / ".vaultspec" / "rules" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        for name in names:
            d = skills_dir / name
            d.mkdir()
            content = f"---\ndescription: {name}\n---\n\nbody"
            (d / "SKILL.md").write_text(content, encoding="utf-8")

    def test_creates_skill_dirs(self, test_project):
        self._make_skill_sources(test_project, ["vaultspec-deploy"])
        skills_sync()
        dest_md = test_project / ".claude" / "skills" / "vaultspec-deploy" / "SKILL.md"
        assert dest_md.exists()
        shared_dest = (
            test_project / ".agents" / "skills" / "vaultspec-deploy" / "SKILL.md"
        )
        assert shared_dest.exists()

    def test_prune_respects_protected(self, test_project):
        # Protected skills like 'fd' or 'rg' shouldn't be pruned
        skills_dir = test_project / ".claude" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        (skills_dir / "fd").mkdir()
        (skills_dir / "fd" / "SKILL.md").write_text("protected", encoding="utf-8")
        (skills_dir / "vaultspec-old").mkdir()
        (skills_dir / "vaultspec-old" / "SKILL.md").write_text(
            "stale", encoding="utf-8"
        )

        self._make_skill_sources(test_project, ["vaultspec-deploy"])
        skills_sync(prune=True)
        assert (skills_dir / "fd" / "SKILL.md").exists()
        assert not (skills_dir / "vaultspec-old" / "SKILL.md").exists()


class TestSyncAgents:
    def test_codex_writes_managed_agents_block(self, test_project):
        agents_dir = test_project / ".vaultspec" / "rules" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "vaultspec-worker.md").write_text(
            "---\n"
            "description: worker\n"
            "codex_model: gpt-5-codex\n"
            "codex_approval_policy: on-request\n"
            "---\n\n"
            "# Worker\n\nImplement carefully.",
            encoding="utf-8",
        )

        agents_sync()

        codex_cfg = test_project / ".codex" / "config.toml"
        assert codex_cfg.exists()
        content = codex_cfg.read_text(encoding="utf-8")
        assert "# BEGIN VAULTSPEC MANAGED CODEX AGENTS" in content
        assert '[agents."vaultspec-worker"]' in content
        assert 'description = "worker"' in content
        assert 'model = "gpt-5-codex"' in content
        assert 'approval_policy = "on-request"' in content
        assert "Implement carefully." in content

    def test_codex_omits_non_codex_generic_model_metadata(self, test_project):
        agents_dir = test_project / ".vaultspec" / "rules" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "gemini-test.md").write_text(
            "---\n"
            "description: calculator\n"
            "model: gemini-2.5-flash\n"
            "---\n\n"
            "# Gemini Test\n\nCalculate.",
            encoding="utf-8",
        )

        agents_sync()

        content = (test_project / ".codex" / "config.toml").read_text(encoding="utf-8")
        assert '[agents."gemini-test"]' in content
        assert 'description = "calculator"' in content
        assert 'model = "gemini-2.5-flash"' not in content

    def test_codex_preserves_user_toml_while_updating_managed_block(self, test_project):
        agents_dir = test_project / ".vaultspec" / "rules" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        agent_path = agents_dir / "vaultspec-worker.md"
        agent_path.write_text(
            "---\ndescription: worker\n---\n\n# Worker\n\nv1 prompt",
            encoding="utf-8",
        )
        codex_cfg = test_project / ".codex" / "config.toml"
        codex_cfg.parent.mkdir(parents=True, exist_ok=True)
        codex_cfg.write_text('model = "gpt-5"\n', encoding="utf-8")

        agents_sync()
        agent_path.write_text(
            "---\ndescription: worker\n---\n\n# Worker\n\nv2 prompt",
            encoding="utf-8",
        )
        agents_sync()

        content = codex_cfg.read_text(encoding="utf-8")
        assert 'model = "gpt-5"' in content
        assert "v2 prompt" in content


class TestSystemSync:
    def test_generates_from_parts(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base system prompt", encoding="utf-8"
        )
        system_sync()
        # Only gemini has system_file
        system_file = test_project / ".gemini" / "SYSTEM.md"
        assert system_file.exists()

    def test_force_overwrites_custom(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )
        system_file = test_project / ".gemini" / "SYSTEM.md"
        system_file.write_text("# Custom", encoding="utf-8")
        # Should skip by default
        system_sync()
        assert system_file.read_text(encoding="utf-8") == "# Custom"
        # Force overwrites
        system_sync(force=True)
        assert "AUTO-GENERATED" in system_file.read_text(encoding="utf-8")


class TestSystemSyncBehavioralRules:
    def test_generates_behavioral_rule_for_claude(self, test_project):
        """system_sync generates vaultspec-system.builtin.md for Claude."""
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Core mandates", encoding="utf-8"
        )
        system_sync()
        rule_file = test_project / ".claude" / "rules" / "vaultspec-system.builtin.md"
        assert rule_file.exists()

    def test_system_sync_produces_both_outputs(self, test_project):
        """system_sync generates SYSTEM.md for Gemini AND rule for Claude."""
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base prompt", encoding="utf-8"
        )
        system_sync()
        assert (test_project / ".gemini" / "SYSTEM.md").exists()
        dest_rule = test_project / ".claude" / "rules" / "vaultspec-system.builtin.md"
        assert dest_rule.exists()

    def test_system_sync_skips_antigravity_and_codex_rule_fallback(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base prompt", encoding="utf-8"
        )
        system_sync()
        assert not (
            test_project / ".agents" / "rules" / "vaultspec-system.builtin.md"
        ).exists()


class TestConfigSync:
    def test_generates_from_internal_and_custom(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "Internal instructions here", encoding="utf-8"
        )
        (test_project / ".vaultspec" / "rules" / "system" / "project.md").write_text(
            "Custom user content", encoding="utf-8"
        )
        config_sync()
        config_file = test_project / ".claude" / "CLAUDE.md"
        assert config_file.exists()
        content = config_file.read_text(encoding="utf-8")
        assert "Custom user content" in content

    def test_force_overwrites_custom_dest(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "Internal", encoding="utf-8"
        )
        config_file = test_project / ".claude" / "CLAUDE.md"
        config_file.write_text("# Hand-written", encoding="utf-8")
        config_sync()
        assert config_file.read_text(encoding="utf-8") == "# Hand-written"
        config_sync(force=True)
        assert "AUTO-GENERATED" in config_file.read_text(encoding="utf-8")

    def test_generates_root_configs_for_antigravity_and_codex(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "Internal instructions here", encoding="utf-8"
        )
        (test_project / ".agents" / "rules").mkdir(parents=True, exist_ok=True)
        (test_project / ".agents" / "rules" / "antigravity-rule.md").write_text(
            "---\nname: antigravity\n---\n\nRule", encoding="utf-8"
        )

        config_sync()

        antigravity_config = test_project / "GEMINI.md"
        codex_config = test_project / "AGENTS.md"
        assert antigravity_config.exists()
        assert codex_config.exists()
        assert "@.agents/rules/antigravity-rule.md" in antigravity_config.read_text(
            encoding="utf-8"
        )
        codex_content = codex_config.read_text(encoding="utf-8")
        assert "Internal instructions here" in codex_content
        assert "@.agents/rules/antigravity-rule.md" not in codex_content

    def test_codex_writes_managed_top_level_config_block(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "---\n"
            "codex_model: gpt-5-codex\n"
            "codex_approval_policy: on-request\n"
            "codex_project_doc_fallback_filenames:\n"
            "  - AGENTS.md\n"
            "  - CLAUDE.md\n"
            "---\n\nInternal instructions here",
            encoding="utf-8",
        )

        config_sync()

        codex_native = test_project / ".codex" / "config.toml"
        content = codex_native.read_text(encoding="utf-8")
        assert "# BEGIN VAULTSPEC MANAGED CODEX CONFIG" in content
        assert 'model = "gpt-5-codex"' in content
        assert 'approval_policy = "on-request"' in content
        assert 'project_doc_fallback_filenames = ["AGENTS.md", "CLAUDE.md"]' in content

    def test_codex_preserves_agents_block_while_updating_top_level_config(
        self, test_project
    ):
        agents_dir = test_project / ".vaultspec" / "rules" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "vaultspec-worker.md").write_text(
            "---\ndescription: worker\n---\n\n# Worker\n\nPrompt",
            encoding="utf-8",
        )
        agents_sync()

        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "---\ncodex_sandbox_mode: workspace-write\n---\n\nInternal",
            encoding="utf-8",
        )
        config_sync()

        content = (test_project / ".codex" / "config.toml").read_text(encoding="utf-8")
        assert "# BEGIN VAULTSPEC MANAGED CODEX CONFIG" in content
        assert 'sandbox_mode = "workspace-write"' in content
        assert '[agents."vaultspec-worker"]' in content

    def test_codex_writes_reasoning_and_service_tier_settings(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "---\n"
            "codex_model_reasoning_effort: medium\n"
            "codex_model_reasoning_summary: concise\n"
            "codex_model_supports_reasoning_summaries: false\n"
            "codex_model_verbosity: high\n"
            "codex_service_tier: priority\n"
            "---\n\nInternal instructions here",
            encoding="utf-8",
        )

        config_sync()

        content = (test_project / ".codex" / "config.toml").read_text(encoding="utf-8")
        assert 'model_reasoning_effort = "medium"' in content
        assert 'model_reasoning_summary = "concise"' in content
        assert "model_supports_reasoning_summaries = false" in content
        assert 'model_verbosity = "high"' in content
        assert 'service_tier = "priority"' in content


class TestEndToEnd:
    def test_full_sync_cycle(self, test_project):
        """Create sources -> sync -> verify destinations."""
        # Set up source files
        (test_project / ".vaultspec" / "rules" / "rules" / "no-swear.md").write_text(
            "---\nname: no-swear\n---\n\nDo not swear.", encoding="utf-8"
        )
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "framework", encoding="utf-8"
        )

        rules_sync()
        skills_sync()
        config_sync()
        system_sync()

        # Verify
        assert (test_project / ".claude" / "rules" / "no-swear.md").exists()
        assert (test_project / ".claude" / "CLAUDE.md").exists()
        assert (test_project / ".gemini" / "SYSTEM.md").exists()

    def test_modify_resync_cycle(self, test_project):
        rule_src = test_project / ".vaultspec" / "rules" / "rules" / "rule1.md"
        rule_src.write_text("---\nname: rule1\n---\n\nOriginal body.", encoding="utf-8")
        rules_sync()
        dest = test_project / ".claude" / "rules" / "rule1.md"
        assert dest.exists()

        rule_src.write_text("---\nname: rule1\n---\n\nMODIFIED", encoding="utf-8")
        rules_sync()
        assert "MODIFIED" in dest.read_text(encoding="utf-8")

    def test_prune_cycle(self, test_project):
        rule_src = test_project / ".vaultspec" / "rules" / "rules" / "ephemeral.md"
        rule_src.write_text("---\nname: ephemeral\n---\n\nGone soon.", encoding="utf-8")
        rules_sync()
        dest = test_project / ".claude" / "rules" / "ephemeral.md"
        assert dest.exists()

        rule_src.unlink()
        rules_sync(prune=True)
        assert not dest.exists()

    def test_force_overwrite_cycle(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "Internal", encoding="utf-8"
        )
        config_file = test_project / ".claude" / "CLAUDE.md"
        config_file.write_text("# Custom", encoding="utf-8")
        config_sync()
        assert config_file.read_text(encoding="utf-8") == "# Custom"
        config_sync(force=True)
        assert "AUTO-GENERATED" in config_file.read_text(encoding="utf-8")
