"""Sync operation tests for the CLI sync engine.

Covers: sync_files, sync_skills, system_sync, config_sync, end-to-end cycles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import cli
import pytest

from .conftest import (  # type: ignore[unresolved-import]
    TEST_PROJECT,
    make_ns,
)

pytestmark = [pytest.mark.unit]


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
        sources = self._make_skill_sources(TEST_PROJECT, ["vaultspec-deploy"])
        result = cli.sync_skills(
            sources=sources,
            skills_dir=skills_dir,
            transform_fn=lambda _t, n, m, b: cli.transform_skill("claude", n, m, b),
            prune=False,
            dry_run=False,
            label="test",
        )
        assert result.added == 1
        assert (skills_dir / "vaultspec-deploy" / "SKILL.md").exists()

    def test_prune_respects_protected(self):
        skills_dir = TEST_PROJECT / "skills"
        # Create a protected skill directory
        (skills_dir / "fd").mkdir(parents=True)
        (skills_dir / "fd" / "SKILL.md").write_text("protected", encoding="utf-8")
        # Create a non-protected vaultspec- skill directory to prune
        (skills_dir / "vaultspec-old").mkdir(parents=True)
        (skills_dir / "vaultspec-old" / "SKILL.md").write_text(
            "stale", encoding="utf-8"
        )

        sources = self._make_skill_sources(TEST_PROJECT, ["vaultspec-deploy"])
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
        # Stale vaultspec- skill pruned
        assert result.pruned == 1
        assert not (skills_dir / "vaultspec-old" / "SKILL.md").exists()

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
        args = make_ns()
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
        args = make_ns()
        cli.system_sync(args)
        content = system_file.read_text(encoding="utf-8")
        assert content == "# My custom system prompt"

    def test_force_overwrites_custom(self):
        (TEST_PROJECT / ".vaultspec" / "system" / "base.md").write_text(
            "---\n---\n\n# Base", encoding="utf-8"
        )
        system_file = TEST_PROJECT / ".gemini" / "SYSTEM.md"
        system_file.write_text("# Custom", encoding="utf-8")
        args = make_ns(force=True)
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
        args = make_ns()
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
        args = make_ns()
        cli.config_sync(args)
        config_file = TEST_PROJECT / ".claude" / "CLAUDE.md"
        assert config_file.exists()

    def test_skips_when_no_internal(self):
        args = make_ns()
        cli.config_sync(args)
        config_file = TEST_PROJECT / ".claude" / "CLAUDE.md"
        assert not config_file.exists()

    def test_skips_custom_dest_without_force(self):
        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "Internal", encoding="utf-8"
        )
        config_file = TEST_PROJECT / ".claude" / "CLAUDE.md"
        config_file.write_text("# Hand-written config", encoding="utf-8")
        args = make_ns()
        cli.config_sync(args)
        content = config_file.read_text(encoding="utf-8")
        assert content == "# Hand-written config"

    def test_force_overwrites_custom_dest(self):
        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "Internal", encoding="utf-8"
        )
        config_file = TEST_PROJECT / ".claude" / "CLAUDE.md"
        config_file.write_text("# Hand-written", encoding="utf-8")
        args = make_ns(force=True)
        cli.config_sync(args)
        content = config_file.read_text(encoding="utf-8")
        assert content.startswith(cli.CONFIG_HEADER)


class TestEndToEnd:
    def test_full_sync_cycle(self):
        """Create sources -> sync -> verify destinations."""
        # Set up source files
        (TEST_PROJECT / ".vaultspec" / "rules" / "no-swear.md").write_text(
            "---\nname: no-swear\n---\n\nDo not swear.", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "agents" / "reviewer.md").write_text(
            "---\ndescription: Reviews code\ntier: MEDIUM\n---\n\n# Reviewer",
            encoding="utf-8",
        )
        (TEST_PROJECT / ".vaultspec" / "skills" / "vaultspec-lint.md").write_text(
            "---\ndescription: Run linter\n---\n\n# Lint", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "Be helpful.", encoding="utf-8"
        )
        (TEST_PROJECT / ".vaultspec" / "system" / "base.md").write_text(
            "---\n---\n\n# You are an assistant.", encoding="utf-8"
        )

        # Sync all
        args = make_ns()
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
        assert (
            TEST_PROJECT / ".claude" / "skills" / "vaultspec-lint" / "SKILL.md"
        ).exists()

        # Verify config
        assert (TEST_PROJECT / ".claude" / "CLAUDE.md").exists()

        # Verify system
        assert (TEST_PROJECT / ".gemini" / "SYSTEM.md").exists()

    def test_modify_resync_cycle(self):
        """Sync -> modify source -> sync -> verify update."""
        rule_src = TEST_PROJECT / ".vaultspec" / "rules" / "rule1.md"
        rule_src.write_text("---\nname: rule1\n---\n\nOriginal body.", encoding="utf-8")
        args = make_ns()
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

    def test_prune_cycle(self):
        """Sync -> delete source -> sync --prune -> verify deletion."""
        rule_src = TEST_PROJECT / ".vaultspec" / "rules" / "ephemeral.md"
        rule_src.write_text("---\nname: ephemeral\n---\n\nGone soon.", encoding="utf-8")
        args = make_ns()
        cli.rules_sync(args)

        dest = TEST_PROJECT / ".claude" / "rules" / "ephemeral.md"
        assert dest.exists()

        # Delete source and re-sync with prune
        rule_src.unlink()
        args_prune = make_ns(prune=True)
        cli.rules_sync(args_prune)
        assert not dest.exists()

    def test_force_overwrite_cycle(self):
        """Create custom dest -> sync (skip) -> sync --force (overwrite)."""
        (TEST_PROJECT / ".vaultspec" / "FRAMEWORK.md").write_text(
            "Internal content", encoding="utf-8"
        )

        config_file = TEST_PROJECT / ".claude" / "CLAUDE.md"
        config_file.write_text("# My hand-written config", encoding="utf-8")

        # Normal sync should skip custom config
        args = make_ns()
        cli.config_sync(args)
        content = config_file.read_text(encoding="utf-8")
        assert content == "# My hand-written config"

        # Force sync overwrites
        args_force = make_ns(force=True)
        cli.config_sync(args_force)
        content = config_file.read_text(encoding="utf-8")
        assert content.startswith(cli.CONFIG_HEADER)
        assert "# My hand-written config" not in content
