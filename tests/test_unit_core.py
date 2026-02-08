from __future__ import annotations

import pathlib

import pytest
from vault.parser import parse_frontmatter

from orchestration.dispatch import (
    AgentNotFoundError,
    load_agent,
)
from orchestration.utils import (
    SecurityError,
    safe_read_text,
)

# ---------------------------------------------------------------------------
# TestParseFrontmatter
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_valid_frontmatter(self):
        content = (
            "---\ntier: LOW\nmodel: gemini-2.5-flash\n---\n\n# Persona\nBody text here."
        )
        meta, body = parse_frontmatter(content)
        assert meta["tier"] == "LOW"
        assert meta["model"] == "gemini-2.5-flash"
        assert "# Persona" in body

    def test_no_frontmatter(self):
        content = "Just plain body text without frontmatter."
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_empty_frontmatter(self):
        content = "---\n\n---\nBody after empty frontmatter."
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert "Body after empty frontmatter." in body

    def test_colon_in_value(self):
        content = "---\ndescription: A test: with colons: everywhere\n---\nBody."
        meta, _body = parse_frontmatter(content)
        assert meta["description"] == "A test: with colons: everywhere"

    def test_quoted_description(self):
        content = (
            "---\n"
            'description: "A quoted description with special chars"\n'
            "tier: HIGH\n"
            "---\n"
            "Body."
        )
        meta, _body = parse_frontmatter(content)
        assert meta["description"] == '"A quoted description with special chars"'
        assert meta["tier"] == "HIGH"

    def test_whitespace_handling(self):
        content = "---\n  key  :  value with spaces  \n---\nBody."
        meta, _body = parse_frontmatter(content)
        assert meta["key"] == "value with spaces"

    def test_body_preserved(self):
        content = "---\ntier: LOW\n---\nLine 1\nLine 2\nLine 3"
        _meta, body = parse_frontmatter(content)
        assert body == "Line 1\nLine 2\nLine 3"


# ---------------------------------------------------------------------------
# TestSafeReadText
# ---------------------------------------------------------------------------


class TestSafeReadText:
    def test_read_existing_file(self, mock_root_dir):
        test_file = mock_root_dir / "test.txt"
        # Library safe_read_text now takes root_dir explicitly
        result = safe_read_text(test_file, mock_root_dir)
        assert "Hello from test workspace" in result

    def test_read_nonexistent_file(self, mock_root_dir):
        missing = mock_root_dir / "nonexistent.txt"
        with pytest.raises(FileNotFoundError):
            safe_read_text(missing, mock_root_dir)

    def test_path_outside_workspace_raises(self, mock_root_dir):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            outside_file = pathlib.Path(td) / "secret.txt"
            outside_file.write_text("secret data", encoding="utf-8")
            with pytest.raises(SecurityError):
                safe_read_text(outside_file, mock_root_dir)


# ---------------------------------------------------------------------------
# TestLoadAgent
# ---------------------------------------------------------------------------


class TestLoadAgent:
    def test_loads_from_canonical(self, mock_root_dir, test_agent_md):
        (mock_root_dir / ".rules" / "agents" / "test-agent.md").write_text(
            test_agent_md, encoding="utf-8"
        )
        # load_agent now takes root_dir
        meta, persona = load_agent("test-agent", mock_root_dir)
        assert meta["tier"] == "LOW"
        assert "French Baker" in persona

    def test_provider_hint_claude(self, mock_root_dir, test_agent_md):
        # Write to both claude and rules dirs
        (mock_root_dir / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
        (mock_root_dir / ".claude" / "agents" / "test-agent.md").write_text(
            "---\n"
            "tier: HIGH\n"
            "model: claude-opus-4-6\n"
            "---\n"
            "# Claude Persona\n"
            "Claude specific.",
            encoding="utf-8",
        )
        (mock_root_dir / ".rules" / "agents").mkdir(parents=True, exist_ok=True)
        (mock_root_dir / ".rules" / "agents" / "test-agent.md").write_text(
            test_agent_md, encoding="utf-8"
        )

        meta, persona = load_agent("test-agent", mock_root_dir, provider_name="claude")
        assert meta["model"] == "claude-opus-4-6"
        assert "Claude Persona" in persona

    def test_provider_hint_gemini(self, mock_root_dir, test_agent_md):
        (mock_root_dir / ".gemini" / "agents").mkdir(parents=True, exist_ok=True)
        (mock_root_dir / ".gemini" / "agents" / "test-agent.md").write_text(
            "---\n"
            "tier: MEDIUM\n"
            "model: gemini-3-flash-preview\n"
            "---\n"
            "# Gemini Persona\n"
            "Gemini specific.",
            encoding="utf-8",
        )
        (mock_root_dir / ".rules" / "agents").mkdir(parents=True, exist_ok=True)
        (mock_root_dir / ".rules" / "agents" / "test-agent.md").write_text(
            test_agent_md, encoding="utf-8"
        )

        meta, _persona = load_agent("test-agent", mock_root_dir, provider_name="gemini")
        assert meta["model"] == "gemini-3-flash-preview"

    def test_provider_hint_falls_back_to_canonical(self, mock_root_dir, test_agent_md):
        # Only canonical dir has the agent
        (mock_root_dir / ".rules" / "agents" / "test-agent.md").write_text(
            test_agent_md, encoding="utf-8"
        )
        meta, _persona = load_agent("test-agent", mock_root_dir, provider_name="claude")
        assert meta["tier"] == "LOW"  # Falls back to canonical

    def test_agent_not_found_raises(self, mock_root_dir):
        with pytest.raises(AgentNotFoundError):
            load_agent("nonexistent-agent", mock_root_dir)

    def test_agent_not_found_with_provider_raises(self, mock_root_dir):
        with pytest.raises(AgentNotFoundError):
            load_agent("nonexistent-agent", mock_root_dir, provider_name="gemini")
