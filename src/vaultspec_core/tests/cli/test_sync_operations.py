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

    def test_adds_new_files(self, synthetic_project):
        dest = synthetic_project / "dest"
        dest.mkdir()
        sources = self._make_sources(synthetic_project, ["a.md", "b.md"])
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

    def test_updates_existing_files(self, synthetic_project):
        dest = synthetic_project / "dest"
        dest.mkdir()
        (dest / "a.md").write_text("old", encoding="utf-8")
        sources = self._make_sources(synthetic_project, ["a.md"])
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

    def test_skips_unchanged_files(self, synthetic_project):
        dest = synthetic_project / "dest"
        dest.mkdir()
        sources = self._make_sources(synthetic_project, ["a.md"])
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

    def test_prune_removes_stale(self, synthetic_project):
        dest = synthetic_project / "dest"
        dest.mkdir()
        (dest / "stale.md").write_text(
            "---\nname: stale\ntrigger: always_on\n---\n\nold stale content",
            encoding="utf-8",
        )
        sources = self._make_sources(synthetic_project, ["a.md"])
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
            d.mkdir(exist_ok=True)
            content = f"---\ndescription: {name}\n---\n\nbody"
            (d / "SKILL.md").write_text(content, encoding="utf-8")

    def test_creates_skill_dirs(self, synthetic_project):
        self._make_skill_sources(synthetic_project, ["vaultspec-deploy"])
        skills_sync()
        dest_md = (
            synthetic_project / ".claude" / "skills" / "vaultspec-deploy" / "SKILL.md"
        )
        assert dest_md.exists()
        shared_dest = (
            synthetic_project / ".agents" / "skills" / "vaultspec-deploy" / "SKILL.md"
        )
        assert shared_dest.exists()

    def test_prune_respects_protected(self, synthetic_project):
        # Directories without a SKILL.md (e.g. user tooling) shouldn't be pruned.
        # Directories with a SKILL.md that are no longer in sources ARE pruned.
        skills_dir = synthetic_project / ".claude" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        # User-placed directory without SKILL.md  - must survive pruning
        user_dir = skills_dir / "my-user-tool"
        user_dir.mkdir(exist_ok=True)
        # Remove any stale SKILL.md so this is truly a non-skill directory
        stale_skill = user_dir / "SKILL.md"
        if stale_skill.exists():
            stale_skill.unlink()
        (user_dir / "README.md").write_text("user tool", encoding="utf-8")
        # Stale synced skill with SKILL.md  - should be pruned
        stale_dir = skills_dir / "vaultspec-stale-test"
        stale_dir.mkdir(exist_ok=True)
        (stale_dir / "SKILL.md").write_text("stale", encoding="utf-8")

        self._make_skill_sources(synthetic_project, ["vaultspec-deploy"])
        skills_sync(prune=True)
        assert (user_dir / "README.md").exists()
        assert not (stale_dir / "SKILL.md").exists()


class TestSyncAgents:
    def test_codex_writes_managed_agents_block(self, synthetic_project):
        agents_dir = synthetic_project / ".vaultspec" / "rules" / "agents"
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

        codex_cfg = synthetic_project / ".codex" / "config.toml"
        assert codex_cfg.exists()
        content = codex_cfg.read_text(encoding="utf-8")
        assert '# <vaultspec type="agents">' in content
        assert '[agents."vaultspec-worker"]' in content
        assert 'description = "worker"' in content
        assert 'model = "gpt-5-codex"' in content
        assert 'approval_policy = "on-request"' in content
        assert "Implement carefully." in content

    def test_codex_omits_non_codex_generic_model_metadata(self, synthetic_project):
        agents_dir = synthetic_project / ".vaultspec" / "rules" / "agents"
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

        content = (synthetic_project / ".codex" / "config.toml").read_text(
            encoding="utf-8"
        )
        assert '[agents."gemini-test"]' in content
        assert 'description = "calculator"' in content
        assert 'model = "gemini-2.5-flash"' not in content

    def test_codex_preserves_user_toml_while_updating_managed_block(
        self, synthetic_project
    ):
        agents_dir = synthetic_project / ".vaultspec" / "rules" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        agent_path = agents_dir / "vaultspec-worker.md"
        agent_path.write_text(
            "---\ndescription: worker\n---\n\n# Worker\n\nv1 prompt",
            encoding="utf-8",
        )
        codex_cfg = synthetic_project / ".codex" / "config.toml"
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


class TestSyncSkillsCodex:
    """Verify skills sync lands in .agents/skills/ for Codex destination."""

    def _make_skill_sources(self, root: Path, names: list[str]):
        skills_dir = root / ".vaultspec" / "rules" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        for name in names:
            d = skills_dir / name
            d.mkdir(exist_ok=True)
            content = f"---\ndescription: {name}\n---\n\n# {name}"
            (d / "SKILL.md").write_text(content, encoding="utf-8")

    def test_codex_skills_land_in_shared_agents_skills(self, synthetic_project):
        """Skills sync writes to .agents/skills/ which is shared by Codex."""
        self._make_skill_sources(synthetic_project, ["vaultspec-deploy"])
        skills_sync()
        shared_dest = (
            synthetic_project / ".agents" / "skills" / "vaultspec-deploy" / "SKILL.md"
        )
        assert shared_dest.exists()
        content = shared_dest.read_text(encoding="utf-8")
        assert "vaultspec-deploy" in content

    def test_codex_skills_have_correct_frontmatter(self, synthetic_project):
        """Skills synced to .agents/skills/ have name and description frontmatter."""
        from vaultspec_core.vaultcore import parse_frontmatter

        self._make_skill_sources(synthetic_project, ["vaultspec-research"])
        skills_sync()
        dest = (
            synthetic_project / ".agents" / "skills" / "vaultspec-research" / "SKILL.md"
        )
        content = dest.read_text(encoding="utf-8")
        meta, _body = parse_frontmatter(content)
        assert meta["name"] == "vaultspec-research"
        assert meta["description"] == "vaultspec-research"


class TestSystemSync:
    def test_generates_from_parts(self, synthetic_project):
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base system prompt", encoding="utf-8"
        )
        system_sync()
        # Only gemini has system_file
        system_file = synthetic_project / ".gemini" / "SYSTEM.md"
        assert system_file.exists()

    def test_force_overwrites_custom(self, synthetic_project):
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )
        system_file = synthetic_project / ".gemini" / "SYSTEM.md"
        system_file.write_text("# Custom", encoding="utf-8")
        # Should skip by default
        system_sync()
        assert system_file.read_text(encoding="utf-8") == "# Custom"
        # Force overwrites
        system_sync(force=True)
        assert "AUTO-GENERATED" in system_file.read_text(encoding="utf-8")


class TestSystemSyncBehavioralRules:
    def test_generates_behavioral_rule_for_claude(self, synthetic_project):
        """system_sync generates vaultspec-system.builtin.md for Claude."""
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Core mandates", encoding="utf-8"
        )
        system_sync()
        rule_file = (
            synthetic_project / ".claude" / "rules" / "vaultspec-system.builtin.md"
        )
        assert rule_file.exists()

    def test_system_sync_produces_both_outputs(self, synthetic_project):
        """system_sync generates SYSTEM.md for Gemini AND rule for Claude."""
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base prompt", encoding="utf-8"
        )
        system_sync()
        assert (synthetic_project / ".gemini" / "SYSTEM.md").exists()
        dest_rule = (
            synthetic_project / ".claude" / "rules" / "vaultspec-system.builtin.md"
        )
        assert dest_rule.exists()

    def test_system_sync_skips_antigravity_and_codex_rule_fallback(
        self, synthetic_project
    ):
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base prompt", encoding="utf-8"
        )
        system_sync()
        assert not (
            synthetic_project / ".agents" / "rules" / "vaultspec-system.builtin.md"
        ).exists()


class TestConfigSync:
    def test_generates_from_rule_refs(self, synthetic_project):
        # Config body now only generates rule references from synced rule files
        rules_dir = synthetic_project / ".claude" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        (rules_dir / "my-rule.md").write_text("rule content", encoding="utf-8")
        config_sync()
        config_file = synthetic_project / "CLAUDE.md"
        assert config_file.exists()
        content = config_file.read_text(encoding="utf-8")
        assert "@.claude/rules/my-rule.md" in content

    def test_preserves_user_content_and_adds_managed_block(self, synthetic_project):
        # Create rule files so config body has content to generate
        rules_dir = synthetic_project / ".claude" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        (rules_dir / "my-rule.md").write_text("rule content", encoding="utf-8")
        config_file = synthetic_project / "CLAUDE.md"
        config_file.write_text("# Hand-written", encoding="utf-8")
        config_sync()
        content = config_file.read_text(encoding="utf-8")
        # User content preserved, managed block added alongside.
        assert "# Hand-written" in content
        assert "<vaultspec" in content
        assert "@.claude/rules/my-rule.md" in content

    def test_generates_root_configs_for_antigravity_and_codex(self, synthetic_project):
        # Create rule files in shared .agents/rules/ for antigravity/codex config
        (synthetic_project / ".agents" / "rules").mkdir(parents=True, exist_ok=True)
        (synthetic_project / ".agents" / "rules" / "antigravity-rule.md").write_text(
            "---\nname: antigravity\n---\n\nRule", encoding="utf-8"
        )

        config_sync()

        antigravity_config = synthetic_project / "GEMINI.md"
        assert antigravity_config.exists()
        assert "@.agents/rules/antigravity-rule.md" in antigravity_config.read_text(
            encoding="utf-8"
        )

    def test_codex_writes_managed_top_level_config_block(self, synthetic_project):
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "codex-cfg.md"
        ).write_text(
            "---\n"
            "pipeline: config\n"
            "codex_model: gpt-5-codex\n"
            "codex_approval_policy: on-request\n"
            "codex_project_doc_fallback_filenames:\n"
            "  - AGENTS.md\n"
            "  - CLAUDE.md\n"
            "---\n\nInternal instructions here",
            encoding="utf-8",
        )

        config_sync()

        codex_native = synthetic_project / ".codex" / "config.toml"
        content = codex_native.read_text(encoding="utf-8")
        assert '# <vaultspec type="config">' in content
        assert 'model = "gpt-5-codex"' in content
        assert 'approval_policy = "on-request"' in content
        assert 'project_doc_fallback_filenames = ["AGENTS.md", "CLAUDE.md"]' in content

    def test_codex_preserves_agents_block_while_updating_top_level_config(
        self, synthetic_project
    ):
        agents_dir = synthetic_project / ".vaultspec" / "rules" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "vaultspec-worker.md").write_text(
            "---\ndescription: worker\n---\n\n# Worker\n\nPrompt",
            encoding="utf-8",
        )
        agents_sync()

        sys_dir = synthetic_project / ".vaultspec" / "rules" / "system"
        (sys_dir / "codex-cfg.md").write_text(
            "---\n"
            "pipeline: config\n"
            "codex_sandbox_mode: workspace-write\n"
            "---\n\nInternal",
            encoding="utf-8",
        )
        config_sync()

        content = (synthetic_project / ".codex" / "config.toml").read_text(
            encoding="utf-8"
        )
        assert '# <vaultspec type="config">' in content
        assert 'sandbox_mode = "workspace-write"' in content
        assert '[agents."vaultspec-worker"]' in content

    def test_codex_writes_reasoning_and_service_tier_settings(self, synthetic_project):
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "codex-cfg.md"
        ).write_text(
            "---\n"
            "pipeline: config\n"
            "codex_model_reasoning_effort: medium\n"
            "codex_model_reasoning_summary: concise\n"
            "codex_model_supports_reasoning_summaries: false\n"
            "codex_model_verbosity: high\n"
            "codex_service_tier: priority\n"
            "---\n\nInternal instructions here",
            encoding="utf-8",
        )

        config_sync()

        content = (synthetic_project / ".codex" / "config.toml").read_text(
            encoding="utf-8"
        )
        assert 'model_reasoning_effort = "medium"' in content
        assert 'model_reasoning_summary = "concise"' in content
        assert "model_supports_reasoning_summaries = false" in content
        assert 'model_verbosity = "high"' in content
        assert 'service_tier = "priority"' in content


class TestEndToEnd:
    def test_full_sync_cycle(self, synthetic_project):
        """Create sources -> sync -> verify destinations."""
        # Set up source files
        (
            synthetic_project / ".vaultspec" / "rules" / "rules" / "no-swear.md"
        ).write_text("---\nname: no-swear\n---\n\nDo not swear.", encoding="utf-8")
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base system prompt", encoding="utf-8"
        )

        rules_sync()
        skills_sync()
        config_sync()
        system_sync()

        # Verify
        assert (synthetic_project / ".claude" / "rules" / "no-swear.md").exists()
        # Config is generated from rule refs (rules were synced above)
        assert (synthetic_project / "CLAUDE.md").exists()
        assert (synthetic_project / ".gemini" / "SYSTEM.md").exists()

    def test_modify_resync_cycle(self, synthetic_project):
        rule_src = synthetic_project / ".vaultspec" / "rules" / "rules" / "rule1.md"
        rule_src.write_text("---\nname: rule1\n---\n\nOriginal body.", encoding="utf-8")
        rules_sync()
        dest = synthetic_project / ".claude" / "rules" / "rule1.md"
        assert dest.exists()

        rule_src.write_text("---\nname: rule1\n---\n\nMODIFIED", encoding="utf-8")
        rules_sync()
        assert "MODIFIED" in dest.read_text(encoding="utf-8")

    def test_prune_cycle(self, synthetic_project):
        rule_src = synthetic_project / ".vaultspec" / "rules" / "rules" / "ephemeral.md"
        rule_src.write_text("---\nname: ephemeral\n---\n\nGone soon.", encoding="utf-8")
        rules_sync()
        dest = synthetic_project / ".claude" / "rules" / "ephemeral.md"
        assert dest.exists()

        rule_src.unlink()
        rules_sync(prune=True)
        assert not dest.exists()

    def test_managed_block_coexists_with_user_content(self, synthetic_project):
        # Create rule files so config body has content to generate
        rules_dir = synthetic_project / ".claude" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        (rules_dir / "my-rule.md").write_text("rule content", encoding="utf-8")
        config_file = synthetic_project / "CLAUDE.md"
        config_file.write_text("# Custom user content", encoding="utf-8")
        config_sync()
        content = config_file.read_text(encoding="utf-8")
        # Managed block added alongside user content.
        assert "# Custom user content" in content
        assert "<vaultspec" in content
        assert "@.claude/rules/my-rule.md" in content
        # Second sync updates managed block, preserves user content.
        config_sync()
        content2 = config_file.read_text(encoding="utf-8")
        assert "# Custom user content" in content2


class TestEndToEndAllDestinations:
    """Validate on-disk outputs for all destinations side by side."""

    def test_full_workspace_sync_all_destinations(self, synthetic_project):
        """Full sync produces the correct file tree for every destination."""
        # Set up sources
        (
            synthetic_project / ".vaultspec" / "rules" / "rules" / "no-swear.md"
        ).write_text("---\nname: no-swear\n---\n\nDo not swear.", encoding="utf-8")
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "codex-cfg.md"
        ).write_text(
            "---\n"
            "pipeline: config\n"
            "codex_model: gpt-5-codex\n"
            "codex_approval_policy: on-request\n"
            "---\n\nCodex config settings",
            encoding="utf-8",
        )
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base system prompt", encoding="utf-8"
        )
        skill_dir = (
            synthetic_project / ".vaultspec" / "rules" / "skills" / "vaultspec-deploy"
        )
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: Deploy service\n---\n\n# Deploy", encoding="utf-8"
        )
        agents_dir = synthetic_project / ".vaultspec" / "rules" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "vaultspec-worker.md").write_text(
            "---\ndescription: worker\ncodex_model: gpt-5-codex\n---\n\n# Worker",
            encoding="utf-8",
        )

        # Run all syncs
        rules_sync()
        skills_sync()
        agents_sync()
        system_sync()
        config_sync()

        # === Claude destination ===
        assert (synthetic_project / "CLAUDE.md").exists()
        assert (synthetic_project / ".claude" / "rules" / "no-swear.md").exists()
        assert (
            synthetic_project / ".claude" / "rules" / "vaultspec-system.builtin.md"
        ).exists()
        assert (
            synthetic_project / ".claude" / "skills" / "vaultspec-deploy" / "SKILL.md"
        ).exists()

        # === Gemini destination ===
        assert (synthetic_project / ".gemini" / "rules" / "no-swear.md").exists()
        assert (synthetic_project / ".gemini" / "SYSTEM.md").exists()
        # Gemini skills go to .agents/skills/ (shared), not .gemini/skills/
        assert (
            synthetic_project / ".agents" / "skills" / "vaultspec-deploy" / "SKILL.md"
        ).exists()

        # === Antigravity destination ===
        antigravity_config = synthetic_project / "GEMINI.md"
        assert antigravity_config.exists()
        ag_content = antigravity_config.read_text(encoding="utf-8")
        # Config body now only contains rule references
        assert "@.agents/rules/no-swear.md" in ag_content
        assert (synthetic_project / ".agents" / "rules" / "no-swear.md").exists()
        # Antigravity must NOT get system builtin rule (emit_system_rule=False)
        assert not (
            synthetic_project / ".agents" / "rules" / "vaultspec-system.builtin.md"
        ).exists()

        # === Codex destination ===
        codex_toml = synthetic_project / ".codex" / "config.toml"
        assert codex_toml.exists()
        toml_content = codex_toml.read_text(encoding="utf-8")
        assert 'model = "gpt-5-codex"' in toml_content
        assert '[agents."vaultspec-worker"]' in toml_content

        # Codex rules are synced to .codex/rules/
        assert (synthetic_project / ".codex" / "rules").exists()
        assert (synthetic_project / ".codex" / "rules" / "no-swear.md").exists()

        # AGENTS.md gets rule references from .codex/rules/
        agents_md = synthetic_project / "AGENTS.md"
        assert agents_md.exists()
        agents_content = agents_md.read_text(encoding="utf-8")
        assert "@.codex/rules/no-swear.md" in agents_content

        # Codex gets system builtin rule (emit_system_rule=True)
        assert (
            synthetic_project / ".codex" / "rules" / "vaultspec-system.builtin.md"
        ).exists()

        # Codex must NOT have:
        assert not (synthetic_project / ".codex" / "CODEX.md").exists()
        assert not (synthetic_project / ".codex" / "SYSTEM.md").exists()

    def test_dry_run_writes_nothing(self, synthetic_project):
        """dry_run=True must not create any destination files or directories."""
        (
            synthetic_project / ".vaultspec" / "rules" / "rules" / "dry-rule.md"
        ).write_text("---\nname: dry-rule\n---\n\nDry run test.", encoding="utf-8")
        (
            synthetic_project / ".vaultspec" / "rules" / "system" / "codex-cfg.md"
        ).write_text(
            "---\npipeline: config\ncodex_model: gpt-5-codex\n---\n\nCodex config",
            encoding="utf-8",
        )
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )

        # Remove all destination dirs and root configs to prove
        # dry-run doesn't create them
        import shutil

        for d in [".claude", ".gemini", ".agents", ".codex"]:
            target = synthetic_project / d
            if target.exists():
                shutil.rmtree(target)
        for f in ["CLAUDE.md", "GEMINI.md", "AGENTS.md"]:
            cfg = synthetic_project / f
            if cfg.exists():
                cfg.unlink()

        rules_sync(dry_run=True)
        skills_sync(dry_run=True)
        system_sync(dry_run=True)
        config_sync(dry_run=True)

        # No destination files should exist
        assert not (synthetic_project / ".claude" / "rules" / "dry-rule.md").exists()
        assert not (synthetic_project / ".gemini" / "rules" / "dry-rule.md").exists()
        assert not (synthetic_project / ".agents" / "rules" / "dry-rule.md").exists()
        assert not (synthetic_project / "CLAUDE.md").exists()
        assert not (synthetic_project / ".gemini" / "SYSTEM.md").exists()
        assert not (synthetic_project / "AGENTS.md").exists()

        # No destination directories should be created by dry-run
        assert not (synthetic_project / ".claude").exists()
        assert not (synthetic_project / ".gemini").exists()
        assert not (synthetic_project / ".agents").exists()


class TestDryRunReturnsItems:
    """Verify that dry-run populates SyncResult.items for rendering."""

    def test_rules_sync_dry_run_returns_items(self, synthetic_project):
        (
            synthetic_project / ".vaultspec" / "rules" / "rules" / "my-rule.md"
        ).write_text("---\nname: my-rule\n---\n\nRule body.", encoding="utf-8")
        result = rules_sync(dry_run=True)
        assert result.items, "dry-run must populate items list"
        paths = [p for p, _action in result.items]
        assert any("my-rule" in p for p in paths)

    def test_dry_run_items_have_correct_actions(self, synthetic_project):
        (
            synthetic_project / ".vaultspec" / "rules" / "rules" / "new-rule.md"
        ).write_text("---\nname: new-rule\n---\n\nNew.", encoding="utf-8")
        result = rules_sync(dry_run=True)
        actions = [a for _p, a in result.items]
        assert all(a == "[ADD]" for a in actions)

    def test_system_sync_dry_run_returns_items(self, synthetic_project):
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Base prompt", encoding="utf-8"
        )
        result = system_sync(dry_run=True)
        assert result.items, "system dry-run must populate items list"
