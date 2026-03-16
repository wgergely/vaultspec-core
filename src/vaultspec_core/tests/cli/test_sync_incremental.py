"""Incremental sync tests for the CLI sync engine."""

from __future__ import annotations

import pytest

from ...core import agents_sync, config_sync, rules_sync, skills_sync, system_sync

pytestmark = [pytest.mark.unit]


class TestIncrementalRules:
    def test_add_modify_remove_loop(self, test_project):
        """Standard rule lifecycle."""
        rule_src = test_project / ".vaultspec" / "rules" / "rules" / "rule1.md"
        rule_src.write_text("---\nname: rule1\n---\n\nOriginal body", encoding="utf-8")

        # 1. Add
        rules_sync()
        dest = test_project / ".claude" / "rules" / "rule1.md"
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

    def test_idempotent_resync(self, test_project):
        """Syncing with no changes doesn't update files."""
        rule_src = test_project / ".vaultspec" / "rules" / "rules" / "stable.md"
        rule_src.write_text("---\nname: stable\n---\n\nBody", encoding="utf-8")
        rules_sync()
        dest = test_project / ".claude" / "rules" / "stable.md"
        mtime1 = dest.stat().st_mtime

        rules_sync()
        mtime2 = dest.stat().st_mtime
        assert mtime1 == mtime2

    def test_cross_destination_consistency(self, test_project):
        """Rules are synced to all available tool destinations."""
        (test_project / ".vaultspec" / "rules" / "rules" / "shared.md").write_text(
            "---\nname: shared\n---\n\nShared rule", encoding="utf-8"
        )
        rules_sync()
        for tool_dir in [".claude", ".gemini"]:
            p = test_project / tool_dir / "rules" / "shared.md"
            assert p.exists(), f"Missing in {tool_dir}"

    def test_five_pass_churn(self, test_project):
        """Simulate rapid changes across multiple sync passes."""
        rules_dir = test_project / ".vaultspec" / "rules" / "rules"
        dest = test_project / ".claude" / "rules" / "churn.md"

        for i in range(5):
            (rules_dir / "churn.md").write_text(
                f"---\nname: churn\n---\n\nPass {i}", encoding="utf-8"
            )
            rules_sync()
            assert f"Pass {i}" in dest.read_text(encoding="utf-8")


class TestIncrementalSkills:
    def test_skill_lifecycle(self, test_project):
        """Skill directory and SKILL.md lifecycle."""
        skill_dir = test_project / ".vaultspec" / "rules" / "skills" / "vaultspec-test"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: v1\n---\n\n# v1", encoding="utf-8"
        )

        # 1. Add
        skills_sync()
        dest = test_project / ".claude" / "skills" / "vaultspec-test" / "SKILL.md"
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
    def test_system_add_modify_cycle(self, test_project):
        """System prompt assembly lifecycle."""
        base_src = test_project / ".vaultspec" / "rules" / "system" / "base.md"
        base_src.write_text("---\n---\n\n# Base v1", encoding="utf-8")

        # 1. Initial sync
        system_sync()
        gemini_sys = test_project / ".gemini" / "SYSTEM.md"
        assert gemini_sys.exists()
        assert "# Base v1" in gemini_sys.read_text(encoding="utf-8")

        # 2. Modify part
        base_src.write_text("---\n---\n\n# Base v2", encoding="utf-8")
        system_sync(force=True)
        assert "# Base v2" in gemini_sys.read_text(encoding="utf-8")

    def test_system_idempotent(self, test_project):
        """Syncing system twice with no changes produces identical output."""
        (test_project / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Stable base", encoding="utf-8"
        )
        system_sync(force=True)
        gemini_sys = test_project / ".gemini" / "SYSTEM.md"
        mtime1 = gemini_sys.stat().st_mtime

        import time

        time.sleep(0.1)

        system_sync(force=True)
        mtime2 = gemini_sys.stat().st_mtime
        assert mtime1 == mtime2


class TestIncrementalConfig:
    def test_framework_content_change_propagates(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "v1 framework", encoding="utf-8"
        )
        config_sync(force=True)
        claude_cfg = test_project / "CLAUDE.md"
        assert "v1 framework" in claude_cfg.read_text(encoding="utf-8")

        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "v2 framework", encoding="utf-8"
        )
        config_sync(force=True)
        assert "v2 framework" in claude_cfg.read_text(encoding="utf-8")

    def test_project_content_change_propagates(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "framework", encoding="utf-8"
        )
        (test_project / ".vaultspec" / "rules" / "system" / "project.md").write_text(
            "project v1", encoding="utf-8"
        )
        config_sync(force=True)
        claude_cfg = test_project / "CLAUDE.md"
        assert "project v1" in claude_cfg.read_text(encoding="utf-8")

        (test_project / ".vaultspec" / "rules" / "system" / "project.md").write_text(
            "project v2", encoding="utf-8"
        )
        config_sync(force=True)
        assert "project v2" in claude_cfg.read_text(encoding="utf-8")

    def test_codex_agents_md_tracks_framework_changes(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "v1 framework", encoding="utf-8"
        )
        config_sync(force=True)
        codex_cfg = test_project / "AGENTS.md"
        assert "v1 framework" in codex_cfg.read_text(encoding="utf-8")

        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "v2 framework", encoding="utf-8"
        )
        config_sync(force=True)
        assert "v2 framework" in codex_cfg.read_text(encoding="utf-8")

    def test_codex_native_config_tracks_frontmatter_changes(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "---\ncodex_approval_policy: on-request\n---\n\nv1 framework",
            encoding="utf-8",
        )
        config_sync(force=True)
        codex_cfg = test_project / ".codex" / "config.toml"
        assert 'approval_policy = "on-request"' in codex_cfg.read_text(encoding="utf-8")

        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "---\ncodex_approval_policy: never\n---\n\nv2 framework",
            encoding="utf-8",
        )
        config_sync(force=True)
        assert 'approval_policy = "never"' in codex_cfg.read_text(encoding="utf-8")

    def test_codex_reasoning_settings_track_frontmatter_changes(self, test_project):
        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "---\n"
            "codex_model_reasoning_effort: low\n"
            "codex_model_supports_reasoning_summaries: false\n"
            "---\n\nv1 framework",
            encoding="utf-8",
        )
        config_sync(force=True)
        codex_cfg = test_project / ".codex" / "config.toml"
        content_v1 = codex_cfg.read_text(encoding="utf-8")
        assert 'model_reasoning_effort = "low"' in content_v1
        assert "model_supports_reasoning_summaries = false" in content_v1

        (test_project / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "---\n"
            "codex_model_reasoning_effort: high\n"
            "codex_model_supports_reasoning_summaries: true\n"
            "---\n\nv2 framework",
            encoding="utf-8",
        )
        config_sync(force=True)
        content_v2 = codex_cfg.read_text(encoding="utf-8")
        assert 'model_reasoning_effort = "high"' in content_v2
        assert "model_supports_reasoning_summaries = true" in content_v2


class TestMixedOperations:
    def test_full_mixed_lifecycle(self, test_project):
        """Add rules+skills, sync, modify+remove some, resync."""
        rules_dir = test_project / ".vaultspec" / "rules" / "rules"
        skills_dir = test_project / ".vaultspec" / "rules" / "skills"
        system_dir = test_project / ".vaultspec" / "rules" / "system"

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
        assert (test_project / ".claude" / "rules" / "r1.md").exists()
        assert (
            test_project / ".claude" / "skills" / "vaultspec-s1" / "SKILL.md"
        ).exists()
        assert (test_project / ".gemini" / "SYSTEM.md").exists()

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
        assert "MODIFIED" in (test_project / ".claude" / "rules" / "r1.md").read_text(
            encoding="utf-8"
        )
        assert not (test_project / ".claude" / "rules" / "r2.md").exists()
        assert (
            test_project / ".claude" / "skills" / "vaultspec-s2" / "SKILL.md"
        ).exists()


class TestIncrementalAgents:
    def test_codex_agent_block_tracks_add_modify_remove(self, test_project):
        agents_dir = test_project / ".vaultspec" / "rules" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        agent_path = agents_dir / "vaultspec-worker.md"
        agent_path.write_text(
            "---\ndescription: worker\n---\n\n# Worker\n\nv1",
            encoding="utf-8",
        )

        agents_sync()
        codex_cfg = test_project / ".codex" / "config.toml"
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
