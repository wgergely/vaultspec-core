"""Incremental sync tests for the CLI sync engine."""

from __future__ import annotations

import pytest

from ...core import agents_sync, config_sync, rules_sync, skills_sync, system_sync

pytestmark = [pytest.mark.unit]


class TestIncrementalRules:
    def test_add_modify_remove_loop(self, synthetic_project):
        """Standard rule lifecycle."""
        rule_src = synthetic_project / ".vaultspec" / "rules" / "rules" / "rule1.md"
        rule_src.write_text("---\nname: rule1\n---\n\nOriginal body", encoding="utf-8")

        # 1. Add
        rules_sync()
        dest = synthetic_project / ".claude" / "rules" / "rule1.md"
        assert dest.exists()
        content_v1 = dest.read_text(encoding="utf-8")
        assert "Original body" in content_v1

        # 2. Modify
        rule_src.write_text("---\nname: rule1\n---\n\nUpdated body", encoding="utf-8")
        rules_sync()
        content_v2 = dest.read_text(encoding="utf-8")
        assert "Updated body" in content_v2

        # 3. Remove (with prune)
        rule_src.unlink()
        rules_sync(prune=True)
        assert not dest.exists()

    def test_idempotent_resync(self, synthetic_project):
        """Syncing with no changes doesn't update files."""
        rule_src = synthetic_project / ".vaultspec" / "rules" / "rules" / "stable.md"
        rule_src.write_text("---\nname: stable\n---\n\nBody", encoding="utf-8")
        rules_sync()
        dest = synthetic_project / ".claude" / "rules" / "stable.md"
        mtime1 = dest.stat().st_mtime

        rules_sync()
        mtime2 = dest.stat().st_mtime
        assert mtime1 == mtime2

    def test_cross_destination_consistency(self, synthetic_project):
        """Rules are synced to all available tool destinations."""
        (synthetic_project / ".vaultspec" / "rules" / "rules" / "shared.md").write_text(
            "---\nname: shared\n---\n\nShared rule", encoding="utf-8"
        )
        rules_sync()
        for tool_dir in [".claude", ".gemini"]:
            p = synthetic_project / tool_dir / "rules" / "shared.md"
            assert p.exists(), f"Missing in {tool_dir}"

    def test_five_pass_churn(self, synthetic_project):
        """Simulate rapid changes across multiple sync passes."""
        rules_dir = synthetic_project / ".vaultspec" / "rules" / "rules"
        dest = synthetic_project / ".claude" / "rules" / "churn.md"

        for i in range(5):
            (rules_dir / "churn.md").write_text(
                f"---\nname: churn\n---\n\nPass {i}", encoding="utf-8"
            )
            rules_sync()
            assert f"Pass {i}" in dest.read_text(encoding="utf-8")


class TestIncrementalSkills:
    def test_skill_lifecycle(self, synthetic_project):
        """Skill directory and SKILL.md lifecycle."""
        skill_dir = (
            synthetic_project / ".vaultspec" / "rules" / "skills" / "vaultspec-test"
        )
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: v1\n---\n\n# v1", encoding="utf-8"
        )

        # 1. Add
        skills_sync()
        dest = synthetic_project / ".claude" / "skills" / "vaultspec-test" / "SKILL.md"
        assert dest.exists()
        assert "description: v1" in dest.read_text(encoding="utf-8")

        # 2. Modify
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: v2\n---\n\n# v2", encoding="utf-8"
        )
        skills_sync()
        assert "description: v2" in dest.read_text(encoding="utf-8")

        # 3. Remove
        shutil_rmtree = __import__("shutil").rmtree
        shutil_rmtree(skill_dir)
        skills_sync(prune=True)
        assert not dest.parent.exists()


class TestIncrementalSystem:
    def test_system_add_modify_cycle(self, synthetic_project):
        """System prompt assembly lifecycle."""
        base_src = synthetic_project / ".vaultspec" / "rules" / "system" / "base.md"
        base_src.write_text("---\n---\n\n# Base v1", encoding="utf-8")

        # 1. Initial sync
        system_sync()
        gemini_sys = synthetic_project / ".gemini" / "SYSTEM.md"
        assert gemini_sys.exists()
        assert "# Base v1" in gemini_sys.read_text(encoding="utf-8")

        # 2. Modify part
        base_src.write_text("---\n---\n\n# Base v2", encoding="utf-8")
        system_sync(force=True)
        assert "# Base v2" in gemini_sys.read_text(encoding="utf-8")

    def test_system_idempotent(self, synthetic_project):
        """Syncing system twice with no changes produces identical output."""
        (synthetic_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Stable base", encoding="utf-8"
        )
        system_sync(force=True)
        gemini_sys = synthetic_project / ".gemini" / "SYSTEM.md"
        mtime1 = gemini_sys.stat().st_mtime

        import time

        time.sleep(0.1)

        system_sync(force=True)
        mtime2 = gemini_sys.stat().st_mtime
        assert mtime1 == mtime2


class TestIncrementalConfig:
    def test_rule_ref_change_propagates(self, synthetic_project):
        # Config body now generates @rules/... references from synced rule files.
        rules_dest = synthetic_project / ".claude" / "rules"
        (rules_dest / "alpha.md").write_text("rule alpha", encoding="utf-8")
        config_sync(force=True)
        claude_cfg = synthetic_project / "CLAUDE.md"
        assert "@" in claude_cfg.read_text(encoding="utf-8")
        assert "alpha.md" in claude_cfg.read_text(encoding="utf-8")

        # Add a second rule  - references should update.
        (rules_dest / "beta.md").write_text("rule beta", encoding="utf-8")
        config_sync(force=True)
        content = claude_cfg.read_text(encoding="utf-8")
        assert "alpha.md" in content
        assert "beta.md" in content

    def test_rule_removal_updates_config(self, synthetic_project):
        # Config body reflects which rule files exist in the destination.
        rules_dest = synthetic_project / ".claude" / "rules"
        (rules_dest / "keep.md").write_text("keep rule", encoding="utf-8")
        (rules_dest / "drop.md").write_text("drop rule", encoding="utf-8")
        config_sync(force=True)
        claude_cfg = synthetic_project / "CLAUDE.md"
        content_v1 = claude_cfg.read_text(encoding="utf-8")
        assert "keep.md" in content_v1
        assert "drop.md" in content_v1

        # Remove one rule  - config should update.
        (rules_dest / "drop.md").unlink()
        config_sync(force=True)
        content_v2 = claude_cfg.read_text(encoding="utf-8")
        assert "keep.md" in content_v2
        assert "drop.md" not in content_v2

    def test_codex_config_file_exists_after_install(self, synthetic_project):
        # AGENTS.md is created during scaffold (like CLAUDE.md / GEMINI.md).
        # config_sync with no rule refs should not destroy it.
        config_sync(force=True)
        codex_cfg = synthetic_project / "AGENTS.md"
        assert codex_cfg.exists()

    def test_codex_native_config_tracks_frontmatter_changes(self, synthetic_project):
        sys_dir = synthetic_project / ".vaultspec" / "rules" / "system"
        (sys_dir / "codex-settings.md").write_text(
            "---\n"
            "pipeline: config\n"
            "codex_approval_policy: on-request\n"
            "---\n\nv1 config",
            encoding="utf-8",
        )
        config_sync(force=True)
        codex_cfg = synthetic_project / ".codex" / "config.toml"
        content = codex_cfg.read_text(encoding="utf-8")
        assert 'approval_policy = "on-request"' in content

        (sys_dir / "codex-settings.md").write_text(
            "---\npipeline: config\ncodex_approval_policy: never\n---\n\nv2 config",
            encoding="utf-8",
        )
        config_sync(force=True)
        content = codex_cfg.read_text(encoding="utf-8")
        assert 'approval_policy = "never"' in content

    def test_codex_reasoning_settings_track_changes(self, synthetic_project):
        sys_dir = synthetic_project / ".vaultspec" / "rules" / "system"
        (sys_dir / "codex-reasoning.md").write_text(
            "---\n"
            "pipeline: config\n"
            "codex_model_reasoning_effort: low\n"
            "codex_model_supports_reasoning_summaries: false\n"
            "---\n\nv1 config",
            encoding="utf-8",
        )
        config_sync(force=True)
        codex_cfg = synthetic_project / ".codex" / "config.toml"
        content_v1 = codex_cfg.read_text(encoding="utf-8")
        assert 'model_reasoning_effort = "low"' in content_v1
        assert "model_supports_reasoning_summaries = false" in content_v1

        (sys_dir / "codex-reasoning.md").write_text(
            "---\n"
            "pipeline: config\n"
            "codex_model_reasoning_effort: high\n"
            "codex_model_supports_reasoning_summaries: true\n"
            "---\n\nv2 config",
            encoding="utf-8",
        )
        config_sync(force=True)
        content_v2 = codex_cfg.read_text(encoding="utf-8")
        assert 'model_reasoning_effort = "high"' in content_v2
        assert "model_supports_reasoning_summaries = true" in content_v2


class TestMixedOperations:
    def test_full_mixed_lifecycle(self, synthetic_project):
        """Add rules+skills, sync, modify+remove some, resync."""
        rules_dir = synthetic_project / ".vaultspec" / "rules" / "rules"
        skills_dir = synthetic_project / ".vaultspec" / "rules" / "skills"
        system_dir = synthetic_project / ".vaultspec" / "rules" / "system"

        # --- Setup: add everything ---
        (rules_dir / "r1.md").write_text(
            "---\nname: r1\n---\n\nRule 1", encoding="utf-8"
        )
        (rules_dir / "r2.md").write_text(
            "---\nname: r2\n---\n\nRule 2", encoding="utf-8"
        )
        (skills_dir / "vaultspec-s1").mkdir(parents=True)
        (skills_dir / "vaultspec-s1" / "SKILL.md").write_text(
            "---\ndescription: s1\n---\n\n# s1", encoding="utf-8"
        )
        (system_dir / "base.md").write_text("---\n---\n\n# Base", encoding="utf-8")

        rules_sync()
        skills_sync()
        system_sync()

        # Verify initial state
        assert (synthetic_project / ".claude" / "rules" / "r1.md").exists()
        assert (
            synthetic_project / ".claude" / "skills" / "vaultspec-s1" / "SKILL.md"
        ).exists()
        assert (synthetic_project / ".gemini" / "SYSTEM.md").exists()

        # --- Churn: Modify r1, delete r2, add s2 ---
        (rules_dir / "r1.md").write_text(
            "---\nname: r1\n---\n\nMODIFIED", encoding="utf-8"
        )
        (rules_dir / "r2.md").unlink()
        (skills_dir / "vaultspec-s2").mkdir(parents=True)
        (skills_dir / "vaultspec-s2" / "SKILL.md").write_text(
            "---\ndescription: s2\n---\n\n# s2", encoding="utf-8"
        )

        rules_sync(prune=True)
        skills_sync(prune=True)

        # Verify churned state
        assert "MODIFIED" in (
            synthetic_project / ".claude" / "rules" / "r1.md"
        ).read_text(encoding="utf-8")
        assert not (synthetic_project / ".claude" / "rules" / "r2.md").exists()
        assert (
            synthetic_project / ".claude" / "skills" / "vaultspec-s2" / "SKILL.md"
        ).exists()


class TestIncrementalAgents:
    def test_codex_agent_block_tracks_add_modify_remove(self, synthetic_project):
        agents_dir = synthetic_project / ".vaultspec" / "rules" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        agent_path = agents_dir / "vaultspec-worker.md"
        agent_path.write_text(
            "---\ndescription: worker\n---\n\n# Worker\n\nv1",
            encoding="utf-8",
        )

        agents_sync()
        codex_cfg = synthetic_project / ".codex" / "config.toml"
        assert "v1" in codex_cfg.read_text(encoding="utf-8")

        agent_path.write_text(
            "---\ndescription: worker\n---\n\n# Worker\n\nv2",
            encoding="utf-8",
        )
        agents_sync()
        assert "v2" in codex_cfg.read_text(encoding="utf-8")

        agent_path.unlink()
        agents_sync(prune=True)
        assert '[agents."vaultspec-worker"]' not in codex_cfg.read_text(
            encoding="utf-8"
        )
