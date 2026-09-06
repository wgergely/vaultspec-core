"""Workspace-level contract for Antigravity agent rendering.

Antigravity discovers custom subagents at ``.agents/agents/<name>.md`` in the
workspace. These tests exercise the whole install-and-sync pipeline rather than
the renderer in isolation, so a regression anywhere along it - the
``ToolConfig`` destination, the ``AGENTS`` capability, the renderer registry, or
the sync pass - fails here.

They also pin the other half of the contract: enrolling Antigravity must leave
the Gemini agent output byte-identical.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.builtins import builtins_root
from vaultspec_core.config import reset_config
from vaultspec_core.core.commands import install_run
from vaultspec_core.core.enums import ProviderCapability, Tool
from vaultspec_core.core.types import init_paths
from vaultspec_core.vaultcore import parse_frontmatter

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]


_SOURCE_AGENT_STEMS = frozenset(
    path.stem for path in (builtins_root() / "agents").glob("*.md")
)
assert _SOURCE_AGENT_STEMS, (
    "No source agents ship under builtins/agents/; these tests would assert "
    "over an empty set and pass vacuously."
)


def _install(target: Path, provider: str) -> None:
    reset_config()
    install_run(
        path=target, provider=provider, upgrade=False, dry_run=False, force=False
    )


def _digest_tree(directory: Path) -> dict[str, str]:
    """Map each ``*.md`` file name in *directory* to a digest of its bytes."""
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.glob("*.md"))
    }


class TestAntigravityCapability:
    def test_antigravity_declares_agents_and_targets_dot_agents(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / ".vaultspec").mkdir()
        ctx = init_paths(tmp_path)
        cfg = ctx.tool_configs[Tool.ANTIGRAVITY]

        assert ProviderCapability.AGENTS in cfg.capabilities
        assert cfg.agents_dir == tmp_path / ".agents" / "agents"

    def test_gemini_agents_destination_is_untouched(self, tmp_path: Path) -> None:
        (tmp_path / ".vaultspec").mkdir()
        ctx = init_paths(tmp_path)

        assert ctx.tool_configs[Tool.GEMINI].agents_dir == (
            tmp_path / ".gemini" / "agents"
        )


class TestInstalledAntigravityWorkspace:
    def test_renders_every_source_agent(self, tmp_path: Path) -> None:
        try:
            _install(tmp_path, "all")

            agents_dir = tmp_path / ".agents" / "agents"
            assert agents_dir.is_dir()
            rendered = {path.stem for path in agents_dir.glob("*.md")}
            assert rendered == set(_SOURCE_AGENT_STEMS)
        finally:
            reset_config()

    def test_rendered_agents_carry_only_the_required_frontmatter(
        self, tmp_path: Path
    ) -> None:
        try:
            _install(tmp_path, "all")

            agents_dir = tmp_path / ".agents" / "agents"
            rendered = sorted(agents_dir.glob("*.md"))
            # Guard against a vacuous pass over an empty (or absent) directory.
            assert len(rendered) == len(_SOURCE_AGENT_STEMS)
            for path in rendered:
                meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
                assert set(meta) == {"name", "description"}, path.name
                assert meta["name"] == path.stem
                assert isinstance(meta["description"], str)
                assert meta["description"].strip()
                assert body.strip(), f"{path.name} rendered an empty body"
        finally:
            reset_config()

    def test_antigravity_only_install_still_renders_agents(
        self, tmp_path: Path
    ) -> None:
        """Enrolling Antigravity alone is enough; it does not ride on Gemini."""
        try:
            _install(tmp_path, "antigravity")

            agents_dir = tmp_path / ".agents" / "agents"
            assert {path.stem for path in agents_dir.glob("*.md")} == set(
                _SOURCE_AGENT_STEMS
            )
            assert not (tmp_path / ".gemini" / "agents").exists()
        finally:
            reset_config()


class TestGeminiOutputUnchanged:
    def test_gemini_agent_bytes_are_identical_with_and_without_antigravity(
        self, tmp_path: Path
    ) -> None:
        """The Gemini render must not shift when Antigravity is also enrolled.

        Two real workspaces are installed - one enrolling Gemini alone, one
        enrolling every provider - and their ``.gemini/agents/`` trees are
        compared by content digest. Any cross-contamination between the two
        renderers, or any change to Gemini's destination, shows up as a
        mismatch.
        """
        gemini_only = tmp_path / "gemini-only"
        every_provider = tmp_path / "all"
        gemini_only.mkdir()
        every_provider.mkdir()

        try:
            _install(gemini_only, "gemini")
            baseline = _digest_tree(gemini_only / ".gemini" / "agents")

            _install(every_provider, "all")
            enrolled = _digest_tree(every_provider / ".gemini" / "agents")
        finally:
            reset_config()

        assert baseline, "the gemini-only install rendered no agents"
        assert enrolled == baseline

    def test_gemini_and_antigravity_renders_are_distinct(self, tmp_path: Path) -> None:
        """The two trees must not be copies of one another.

        Without this, the byte-identity test above would still pass if the
        Antigravity destination were accidentally fed the Gemini renderer.
        """
        try:
            _install(tmp_path, "all")

            gemini = _digest_tree(tmp_path / ".gemini" / "agents")
            antigravity = _digest_tree(tmp_path / ".agents" / "agents")
        finally:
            reset_config()

        assert set(gemini) == set(antigravity)
        overlapping = {name for name in gemini if gemini[name] == antigravity[name]}
        assert not overlapping, (
            f"{sorted(overlapping)} rendered identically for Gemini and "
            "Antigravity; the Antigravity renderer is not being applied"
        )
