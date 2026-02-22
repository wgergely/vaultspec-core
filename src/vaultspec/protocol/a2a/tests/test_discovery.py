"""Unit tests for Gemini CLI A2A agent discovery configuration."""

from __future__ import annotations

import json

import pytest

from .. import (
    generate_agent_md,
    write_agent_discovery,
    write_gemini_settings,
)


@pytest.mark.unit
class TestGenerateAgentMd:
    def test_generate_agent_md_content(self):
        """Markdown contains agent_card_url line."""
        md = generate_agent_md(
            "vaultspec-researcher",
            "http://localhost:10010/.well-known/agent.json",
        )
        assert "# vaultspec-researcher" in md
        assert "agent_card_url: http://localhost:10010/.well-known/agent.json" in md

    def test_generate_agent_md_default_description(self):
        """Default description is used when none provided."""
        md = generate_agent_md(
            "writer",
            "http://localhost:10011/.well-known/agent.json",
        )
        assert "Vaultspec writer agent via A2A protocol." in md

    def test_generate_agent_md_custom_description(self):
        """Custom description appears in output."""
        md = generate_agent_md(
            "vaultspec-researcher",
            "http://localhost:10010/.well-known/agent.json",
            description="A deep research agent for code analysis.",
        )
        assert "A deep research agent for code analysis." in md
        # Default description should NOT appear
        assert "Vaultspec vaultspec-researcher agent via A2A protocol." not in md


@pytest.mark.unit
class TestWriteAgentDiscovery:
    def test_write_agent_discovery_creates_file(self, tmp_path):
        """File is created at .gemini/agents/<name>.md."""
        result = write_agent_discovery(tmp_path, "vaultspec-researcher")

        expected = tmp_path / ".gemini" / "agents" / "vaultspec-researcher.md"
        assert result == expected
        assert expected.exists()
        content = expected.read_text(encoding="utf-8")
        assert "# vaultspec-researcher" in content

    def test_write_agent_discovery_url_format(self, tmp_path):
        """URL matches http://host:port/.well-known/agent.json."""
        write_agent_discovery(tmp_path, "writer", host="192.168.1.10", port=10020)

        md_path = tmp_path / ".gemini" / "agents" / "writer.md"
        content = md_path.read_text(encoding="utf-8")
        expected = "agent_card_url: http://192.168.1.10:10020/.well-known/agent.json"
        assert expected in content

    def test_write_agent_discovery_custom_description(self, tmp_path):
        """Custom description is written to the file."""
        write_agent_discovery(
            tmp_path, "analyst", description="Analyzes vault documents."
        )

        md_path = tmp_path / ".gemini" / "agents" / "analyst.md"
        content = md_path.read_text(encoding="utf-8")
        assert "Analyzes vault documents." in content


@pytest.mark.unit
class TestWriteGeminiSettings:
    def test_write_gemini_settings_creates_file(self, tmp_path):
        """settings.json is created with enableAgents=true."""
        result = write_gemini_settings(tmp_path)

        expected = tmp_path / ".gemini" / "settings.json"
        assert result == expected
        assert expected.exists()

        settings = json.loads(expected.read_text(encoding="utf-8"))
        assert settings["experimental"]["enableAgents"] is True

    def test_write_gemini_settings_disable_agents(self, tmp_path):
        """enableAgents can be set to false."""
        write_gemini_settings(tmp_path, enable_agents=False)

        settings_path = tmp_path / ".gemini" / "settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        assert settings["experimental"]["enableAgents"] is False

    def test_write_gemini_settings_preserves_existing(self, tmp_path):
        """Existing keys in settings.json survive the update."""
        settings_dir = tmp_path / ".gemini"
        settings_dir.mkdir(parents=True)
        settings_path = settings_dir / "settings.json"

        existing = {
            "theme": "dark",
            "experimental": {"someOtherFlag": True},
        }
        settings_path.write_text(json.dumps(existing), encoding="utf-8")

        write_gemini_settings(tmp_path)

        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        assert settings["theme"] == "dark"
        assert settings["experimental"]["someOtherFlag"] is True
        assert settings["experimental"]["enableAgents"] is True
