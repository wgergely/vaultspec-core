"""Incremental and multi-pass integration tests for the CLI sync engine.

Covers: multi-pass rule/agent/skill/system/config sync, mixed operations.
"""

from __future__ import annotations

import pytest

import vaultspec.cli as cli
from vaultspec.protocol.providers import ClaudeModels

from .conftest import (
    TEST_PROJECT,
    make_ns,
)

pytestmark = [pytest.mark.unit]


class TestIncrementalRules:
    """Multi-pass rule sync: add, modify, remove, prune across iterations."""

    def test_add_modify_remove_loop(self):
        """Full lifecycle: add/sync/modify/prune."""
        rules_dir = TEST_PROJECT / ".vaultspec" / "rules" / "rules"
        args = make_ns()
        args_prune = make_ns(prune=True)

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

    def test_idempotent_resync(self):
        """Syncing twice with no changes keeps files identical."""
        (TEST_PROJECT / ".vaultspec" / "rules" / "rules" / "stable.md").write_text(
            "---\nname: stable\n---\n\nstable content", encoding="utf-8"
        )
        args = make_ns()
        cli.rules_sync(args)
        content_v1 = (TEST_PROJECT / ".claude" / "rules" / "stable.md").read_text(
            encoding="utf-8"
        )
        cli.rules_sync(args)
        content_v2 = (TEST_PROJECT / ".claude" / "rules" / "stable.md").read_text(
            encoding="utf-8"
        )
        assert content_v1 == content_v2

    def test_cross_destination_consistency(self):
        """All tool destinations get the same body content after sync."""
        (TEST_PROJECT / ".vaultspec" / "rules" / "rules" / "shared.md").write_text(
            "---\nname: shared\n---\n\nshared content here", encoding="utf-8"
        )
        cli.rules_sync(make_ns())

        bodies = {}
        for tool_dir in [".claude", ".gemini", ".agent"]:
            p = TEST_PROJECT / tool_dir / "rules" / "shared.md"
            assert p.exists(), f"Missing in {tool_dir}"
            _meta, body = cli.parse_frontmatter(p.read_text(encoding="utf-8"))
            bodies[tool_dir] = body.strip()

        # All destinations have the same body content
        assert bodies[".claude"] == bodies[".gemini"] == bodies[".agent"]

    def test_five_pass_churn(self):
        """Simulate 5 sync passes with different mutations each time."""
        rules_dir = TEST_PROJECT / ".vaultspec" / "rules" / "rules"
        args = make_ns()
        args_prune = make_ns(prune=True)

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

    def test_agent_lifecycle(self):
        agents_dir = TEST_PROJECT / ".vaultspec" / "rules" / "agents"
        args = make_ns()
        args_prune = make_ns(prune=True)

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

    def test_agent_tier_change(self):
        """Changing an agent's tier changes the resolved model in output."""
        agents_dir = TEST_PROJECT / ".vaultspec" / "rules" / "agents"
        args = make_ns()

        (agents_dir / "flex.md").write_text(
            "---\ndescription: Flexible\ntier: LOW\n---\n\n# Flex",
            encoding="utf-8",
        )
        cli.agents_sync(args)
        c1 = (TEST_PROJECT / ".claude" / "agents" / "flex.md").read_text(
            encoding="utf-8"
        )
        assert ClaudeModels.LOW in c1

        (agents_dir / "flex.md").write_text(
            "---\ndescription: Flexible\ntier: HIGH\n---\n\n# Flex upgraded",
            encoding="utf-8",
        )
        cli.agents_sync(args)
        c2 = (TEST_PROJECT / ".claude" / "agents" / "flex.md").read_text(
            encoding="utf-8"
        )
        assert ClaudeModels.HIGH in c2
        assert "Flex upgraded" in c2


class TestIncrementalSkills:
    """Skill add/modify/remove across sync passes."""

    def test_skill_lifecycle(self):
        skills_dir = TEST_PROJECT / ".vaultspec" / "rules" / "skills"
        args = make_ns()
        args_prune = make_ns(prune=True)

        # Add skill
        (skills_dir / "vaultspec-deploy.md").write_text(
            "---\ndescription: Deploy service\n---\n\n# Deploy v1",
            encoding="utf-8",
        )
        cli.skills_sync(args)
        assert (
            TEST_PROJECT / ".claude" / "skills" / "vaultspec-deploy" / "SKILL.md"
        ).exists()

        # Modify skill
        (skills_dir / "vaultspec-deploy.md").write_text(
            "---\ndescription: Deploy service v2\n---\n\n# Deploy updated",
            encoding="utf-8",
        )
        cli.skills_sync(args)
        content = (
            TEST_PROJECT / ".claude" / "skills" / "vaultspec-deploy" / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert "Deploy updated" in content

        # Add second skill, remove first, prune
        (skills_dir / "vaultspec-test.md").write_text(
            "---\ndescription: Run tests\n---\n\n# Test",
            encoding="utf-8",
        )
        (skills_dir / "vaultspec-deploy.md").unlink()
        cli.skills_sync(args_prune)
        assert not (TEST_PROJECT / ".claude" / "skills" / "vaultspec-deploy").exists()
        assert (
            TEST_PROJECT / ".claude" / "skills" / "vaultspec-test" / "SKILL.md"
        ).exists()


class TestIncrementalSystem:
    """System prompt incremental changes across sync passes."""

    def test_system_add_modify_cycle(self):
        system_dir = TEST_PROJECT / ".vaultspec" / "rules" / "system"
        args = make_ns(force=True)

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
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "base.md").write_text(
            "---\n---\n\n# Stable base", encoding="utf-8"
        )
        args = make_ns(force=True)
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
    """Config sync responds to system/framework.md / system/project.md changes."""

    def test_framework_content_change_propagates(self):
        args = make_ns(force=True)

        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "v1 framework", encoding="utf-8"
        )
        cli.config_sync(args)
        c1 = (TEST_PROJECT / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "v1 framework" in c1

        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "v2 framework", encoding="utf-8"
        )
        cli.config_sync(args)
        c2 = (TEST_PROJECT / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "v2 framework" in c2
        assert "v1 framework" not in c2

    def test_project_content_change_propagates(self):
        args = make_ns(force=True)

        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
            "framework", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "project.md").write_text(
            "project v1", encoding="utf-8"
        )
        cli.config_sync(args)
        c1 = (TEST_PROJECT / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "project v1" in c1

        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "project.md").write_text(
            "project v2", encoding="utf-8"
        )
        cli.config_sync(args)
        c2 = (TEST_PROJECT / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "project v2" in c2
        assert "project v1" not in c2


class TestMixedOperations:
    """Cross-resource-type operations in a single integration flow."""

    def test_full_mixed_lifecycle(self):
        """Add rules+agents+skills, sync, modify+remove some, resync."""
        rules_dir = TEST_PROJECT / ".vaultspec" / "rules" / "rules"
        agents_dir = TEST_PROJECT / ".vaultspec" / "rules" / "agents"
        skills_dir = TEST_PROJECT / ".vaultspec" / "rules" / "skills"
        system_dir = TEST_PROJECT / ".vaultspec" / "rules" / "system"
        args = make_ns()
        args_prune = make_ns(prune=True)

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
        (skills_dir / "vaultspec-build.md").write_text(
            "---\ndescription: Build it\n---\n\n# Build", encoding="utf-8"
        )
        (system_dir / "base.md").write_text(
            "---\n---\n\n# System base", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "rules" / "system" / "framework.md").write_text(
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
            TEST_PROJECT / ".claude" / "skills" / "vaultspec-build" / "SKILL.md"
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
        (skills_dir / "vaultspec-build.md").unlink()

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

        assert not (TEST_PROJECT / ".claude" / "skills" / "vaultspec-build").exists()

        # System prompt should reflect updated agent listing
        system = (TEST_PROJECT / ".gemini" / "SYSTEM.md").read_text(encoding="utf-8")
        assert "Builds fast" in system
