from __future__ import annotations

import pathlib
import tempfile

import pytest

from vaultspec.orchestration import (
    SecurityError,
    safe_read_text,
)
from vaultspec.orchestration.subagent import (
    AgentNotFoundError,
    load_agent,
)
from vaultspec.protocol.providers import ClaudeModels, GeminiModels

pytestmark = [pytest.mark.unit]


class TestSafeReadText:
    def test_read_existing_file(self, test_root_dir):
        test_file = test_root_dir / "test.txt"
        result = safe_read_text(test_file, test_root_dir)
        assert "Hello from test workspace" in result

    def test_read_nonexistent_file(self, test_root_dir):
        missing = test_root_dir / "nonexistent.txt"
        with pytest.raises(FileNotFoundError):
            safe_read_text(missing, test_root_dir)

    def test_path_outside_workspace_raises(self, test_root_dir):
        with tempfile.TemporaryDirectory() as td:
            outside_file = pathlib.Path(td) / "secret.txt"
            outside_file.write_text("secret data", encoding="utf-8")
            with pytest.raises(SecurityError):
                safe_read_text(outside_file, test_root_dir)


class TestLoadAgent:
    def test_loads_from_canonical(self, test_root_dir, test_agent_md):
        (test_root_dir / ".vaultspec" / "rules" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        (
            test_root_dir / ".vaultspec" / "rules" / "agents" / "test-agent.md"
        ).write_text(test_agent_md, encoding="utf-8")
        meta, persona = load_agent("test-agent", test_root_dir)
        assert meta["tier"] == "LOW"
        assert "French Baker" in persona

    def test_provider_hint_claude(self, test_root_dir, test_agent_md):
        agents_dir = test_root_dir / ".vaultspec" / "rules" / "agents"
        (agents_dir / "claude").mkdir(parents=True, exist_ok=True)
        (agents_dir / "claude" / "test-agent.md").write_text(
            "---\n"
            "tier: HIGH\n"
            f"model: {ClaudeModels.HIGH}\n"
            "---\n"
            "# Claude Persona\n"
            "Claude specific.",
            encoding="utf-8",
        )
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "test-agent.md").write_text(test_agent_md, encoding="utf-8")

        meta, persona = load_agent("test-agent", test_root_dir, provider_name="claude")
        assert meta["model"] == ClaudeModels.HIGH
        assert "Claude Persona" in persona

    def test_provider_hint_gemini(self, test_root_dir, test_agent_md):
        agents_dir = test_root_dir / ".vaultspec" / "rules" / "agents"
        (agents_dir / "gemini").mkdir(parents=True, exist_ok=True)
        (agents_dir / "gemini" / "test-agent.md").write_text(
            "---\n"
            "tier: MEDIUM\n"
            f"model: {GeminiModels.HIGH}\n"
            "---\n"
            "# Gemini Persona\n"
            "Gemini specific.",
            encoding="utf-8",
        )
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "test-agent.md").write_text(test_agent_md, encoding="utf-8")

        meta, _persona = load_agent("test-agent", test_root_dir, provider_name="gemini")
        assert meta["model"] == GeminiModels.HIGH

    def test_provider_hint_falls_back_to_canonical(self, test_root_dir, test_agent_md):
        (test_root_dir / ".vaultspec" / "rules" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        (
            test_root_dir / ".vaultspec" / "rules" / "agents" / "test-agent.md"
        ).write_text(test_agent_md, encoding="utf-8")
        meta, _persona = load_agent("test-agent", test_root_dir, provider_name="claude")
        assert meta["tier"] == "LOW"

    def test_agent_not_found_raises(self, test_root_dir):
        with pytest.raises(AgentNotFoundError):
            load_agent("nonexistent-agent", test_root_dir)

    def test_agent_not_found_with_provider_raises(self, test_root_dir):
        with pytest.raises(AgentNotFoundError):
            load_agent("nonexistent-agent", test_root_dir, provider_name="gemini")
