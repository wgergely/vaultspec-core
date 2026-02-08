"""Tests for acp_dispatch.py CLI features.

Covers:
- --list-agents flag (list_available_agents function)
- --mode flag (read-only permission prompt injection)
- Argument validation (--agent required without --list-agents)
- H2: Read-only enforcement in write_text_file()
- H4: InitializeResponse capabilities storage
- M3: Terminal restriction in read-only mode
- GeminiDispatchClient mode parameter
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

# Ensure scripts dir is importable
_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import acp_dispatch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agents_workspace(tmp_path: pathlib.Path, monkeypatch):
    """Set up a temp workspace with agent files for list_available_agents tests."""
    agents_dir = tmp_path / ".rules" / "agents"
    agents_dir.mkdir(parents=True)

    (agents_dir / "test-researcher.md").write_text(
        '---\ndescription: "A test research agent"\ntier: HIGH\n'
        "mode: read-only\ntools: Glob, Grep, Read\n---\n\n# Test Researcher\n",
        encoding="utf-8",
    )
    (agents_dir / "test-executor.md").write_text(
        '---\ndescription: "A test executor agent"\ntier: LOW\n'
        "mode: read-write\ntools: Glob, Grep, Read, Write, Edit, Bash\n---\n\n# Test Executor\n",
        encoding="utf-8",
    )
    (agents_dir / "malformed-agent.md").write_text(
        "No frontmatter here, just plain text.",
        encoding="utf-8",
    )

    monkeypatch.setattr(acp_dispatch, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(
        acp_dispatch,
        "AGENT_DIRS",
        {
            "gemini": tmp_path / ".gemini" / "agents",
            "claude": tmp_path / ".claude" / "agents",
            "antigravity": tmp_path / ".agent" / "agents",
            "rules": agents_dir,
        },
    )

    return tmp_path


@pytest.fixture
def empty_agents_workspace(tmp_path: pathlib.Path, monkeypatch):
    """Set up a workspace with no agents directory."""
    monkeypatch.setattr(acp_dispatch, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(
        acp_dispatch,
        "AGENT_DIRS",
        {
            "gemini": tmp_path / ".gemini" / "agents",
            "claude": tmp_path / ".claude" / "agents",
            "antigravity": tmp_path / ".agent" / "agents",
            "rules": tmp_path / ".rules" / "agents",
        },
    )
    return tmp_path


# ---------------------------------------------------------------------------
# TestListAvailableAgents
# ---------------------------------------------------------------------------

class TestListAvailableAgents:
    """Tests for list_available_agents()."""

    def test_returns_agents(self, agents_workspace):
        agents = acp_dispatch.list_available_agents()
        assert len(agents) == 3

    def test_agent_fields(self, agents_workspace):
        agents = acp_dispatch.list_available_agents()
        by_name = {a["name"]: a for a in agents}

        researcher = by_name["test-researcher"]
        assert researcher["tier"] == "HIGH"
        assert "test research agent" in researcher["description"]

        executor = by_name["test-executor"]
        assert executor["tier"] == "LOW"
        assert "test executor agent" in executor["description"]

    def test_malformed_agent_handled(self, agents_workspace):
        agents = acp_dispatch.list_available_agents()
        by_name = {a["name"]: a for a in agents}
        malformed = by_name["malformed-agent"]
        assert malformed["tier"] == "UNKNOWN"

    def test_sorted_by_name(self, agents_workspace):
        agents = acp_dispatch.list_available_agents()
        names = [a["name"] for a in agents]
        assert names == sorted(names)

    def test_empty_agents_dir(self, empty_agents_workspace):
        agents = acp_dispatch.list_available_agents()
        assert agents == []

    def test_description_quotes_stripped(self, agents_workspace):
        """Double quotes around YAML description values are stripped."""
        agents = acp_dispatch.list_available_agents()
        for agent in agents:
            # No description should start or end with double quotes.
            if agent["description"] and not agent["description"].startswith("(parse"):
                assert not agent["description"].startswith('"')
                assert not agent["description"].endswith('"')


# ---------------------------------------------------------------------------
# TestCliReadonlyPrompt
# ---------------------------------------------------------------------------

class TestCliReadonlyPrompt:
    """Tests for the CLI read-only permission prompt constant."""

    def test_prompt_constant_exists(self):
        assert hasattr(acp_dispatch, "_CLI_READONLY_PERMISSION_PROMPT")

    def test_prompt_contains_readonly(self):
        assert "READ-ONLY" in acp_dispatch._CLI_READONLY_PERMISSION_PROMPT

    def test_prompt_contains_docs_restriction(self):
        assert ".docs/" in acp_dispatch._CLI_READONLY_PERMISSION_PROMPT


# ---------------------------------------------------------------------------
# TestDispatchResult
# ---------------------------------------------------------------------------


class TestDispatchResult:
    """Tests for the DispatchResult dataclass."""

    def test_default_written_files(self):
        result = acp_dispatch.DispatchResult(response_text="hello")
        assert result.response_text == "hello"
        assert result.written_files == []

    def test_with_written_files(self):
        result = acp_dispatch.DispatchResult(
            response_text="done",
            written_files=[".docs/plan.md", "src/lib.rs"],
        )
        assert result.written_files == [".docs/plan.md", "src/lib.rs"]

    def test_frozen(self):
        result = acp_dispatch.DispatchResult(response_text="done")
        with pytest.raises(AttributeError):
            result.response_text = "changed"


# ---------------------------------------------------------------------------
# TestReadOnlyEnforcement (H2)
# ---------------------------------------------------------------------------

class TestReadOnlyEnforcement:
    """Tests for protocol-level read-only enforcement in write_text_file()."""

    def test_readwrite_mode_allows_all_workspace_writes(self, agents_workspace):
        """In read-write mode, writes anywhere in workspace are allowed."""
        client = acp_dispatch.GeminiDispatchClient(mode="read-write")
        # Monkeypatch ROOT_DIR for the client's path validation
        src_file = agents_workspace / "src" / "main.rs"

        async def _test():
            return await client.write_text_file(
                content="fn main() {}",
                path=str(src_file),
                session_id="test-session",
            )

        result = asyncio.run(_test())
        assert result == {}
        assert src_file.exists()
        assert src_file.read_text(encoding="utf-8") == "fn main() {}"

    def test_readonly_mode_allows_docs_writes(self, agents_workspace):
        """In read-only mode, writes to .docs/ are allowed."""
        client = acp_dispatch.GeminiDispatchClient(mode="read-only")
        docs_file = agents_workspace / ".docs" / "plan" / "test.md"

        async def _test():
            return await client.write_text_file(
                content="# Test Plan",
                path=str(docs_file),
                session_id="test-session",
            )

        result = asyncio.run(_test())
        assert result == {}
        assert docs_file.exists()

    def test_readonly_mode_blocks_src_writes(self, agents_workspace):
        """In read-only mode, writes to src/ are rejected."""
        client = acp_dispatch.GeminiDispatchClient(mode="read-only")
        src_file = agents_workspace / "src" / "main.rs"

        async def _test():
            return await client.write_text_file(
                content="fn main() {}",
                path=str(src_file),
                session_id="test-session",
            )

        with pytest.raises(ValueError, match="read-only mode"):
            asyncio.run(_test())
        assert not src_file.exists()

    def test_readonly_mode_blocks_root_writes(self, agents_workspace):
        """In read-only mode, writes to workspace root files are rejected."""
        client = acp_dispatch.GeminiDispatchClient(mode="read-only")
        root_file = agents_workspace / "Cargo.toml"

        async def _test():
            return await client.write_text_file(
                content="[package]",
                path=str(root_file),
                session_id="test-session",
            )

        with pytest.raises(ValueError, match="read-only mode"):
            asyncio.run(_test())

    def test_readonly_mode_blocks_crates_writes(self, agents_workspace):
        """In read-only mode, writes to crates/ are rejected."""
        client = acp_dispatch.GeminiDispatchClient(mode="read-only")
        crate_file = agents_workspace / "crates" / "pp-core" / "src" / "lib.rs"

        async def _test():
            return await client.write_text_file(
                content="pub mod core;",
                path=str(crate_file),
                session_id="test-session",
            )

        with pytest.raises(ValueError, match="read-only mode"):
            asyncio.run(_test())

    def test_readonly_written_files_not_appended_on_block(self, agents_workspace):
        """Blocked writes are NOT added to the written_files list."""
        client = acp_dispatch.GeminiDispatchClient(mode="read-only")
        src_file = agents_workspace / "src" / "main.rs"

        async def _test():
            try:
                await client.write_text_file(
                    content="fn main() {}",
                    path=str(src_file),
                    session_id="test-session",
                )
            except ValueError:
                pass

        asyncio.run(_test())
        assert str(src_file) not in client.written_files
        assert len(client.written_files) == 0

    def test_outside_workspace_rejected_regardless_of_mode(self, agents_workspace):
        """Writes outside the workspace are rejected in any mode."""
        for mode in ("read-write", "read-only"):
            client = acp_dispatch.GeminiDispatchClient(mode=mode)

            async def _test():
                return await client.write_text_file(
                    content="malicious",
                    path="/etc/passwd",
                    session_id="test-session",
                )

            with pytest.raises(ValueError, match="outside workspace"):
                asyncio.run(_test())


# ---------------------------------------------------------------------------
# TestClientCapabilities (H4)
# ---------------------------------------------------------------------------

class TestClientCapabilities:
    """Tests for agent capabilities storage on GeminiDispatchClient."""

    def test_agent_capabilities_initially_none(self):
        """agent_capabilities is None before initialization."""
        client = acp_dispatch.GeminiDispatchClient()
        assert client.agent_capabilities is None

    def test_agent_capabilities_can_be_set(self):
        """agent_capabilities can be stored after initialization."""
        client = acp_dispatch.GeminiDispatchClient()
        mock_caps = {"load_session": True, "mcp_capabilities": {}}
        client.agent_capabilities = mock_caps
        assert client.agent_capabilities == mock_caps

    def test_conn_and_session_initially_none(self):
        """_conn and _session_id are None before initialization."""
        client = acp_dispatch.GeminiDispatchClient()
        assert client._conn is None
        assert client._session_id is None


# ---------------------------------------------------------------------------
# TestClientMode
# ---------------------------------------------------------------------------

class TestClientMode:
    """Tests for the GeminiDispatchClient mode parameter."""

    def test_default_mode_is_readwrite(self):
        """Default mode is read-write."""
        client = acp_dispatch.GeminiDispatchClient()
        assert client.mode == "read-write"

    def test_readonly_mode_stored(self):
        """read-only mode is stored correctly."""
        client = acp_dispatch.GeminiDispatchClient(mode="read-only")
        assert client.mode == "read-only"

    def test_readwrite_mode_stored(self):
        """read-write mode is stored correctly."""
        client = acp_dispatch.GeminiDispatchClient(mode="read-write")
        assert client.mode == "read-write"


# ---------------------------------------------------------------------------
# TestGracefulCancel (M2)
# ---------------------------------------------------------------------------

class TestGracefulCancel:
    """Tests for the graceful_cancel method on GeminiDispatchClient."""

    def test_graceful_cancel_no_conn(self):
        """graceful_cancel does nothing when no connection is set."""
        client = acp_dispatch.GeminiDispatchClient()

        async def _test():
            await client.graceful_cancel()

        # Should not raise
        asyncio.run(_test())

    def test_graceful_cancel_with_conn(self):
        """graceful_cancel sends session/cancel via the connection."""
        from unittest.mock import AsyncMock, MagicMock

        client = acp_dispatch.GeminiDispatchClient()
        mock_conn = MagicMock()
        mock_conn.cancel = AsyncMock()
        client._conn = mock_conn
        client._session_id = "test-session-123"

        async def _test():
            await client.graceful_cancel()

        asyncio.run(_test())
        mock_conn.cancel.assert_called_once_with(session_id="test-session-123")

    def test_graceful_cancel_suppresses_errors(self):
        """graceful_cancel silently handles exceptions."""
        from unittest.mock import AsyncMock, MagicMock

        client = acp_dispatch.GeminiDispatchClient()
        mock_conn = MagicMock()
        mock_conn.cancel = AsyncMock(side_effect=RuntimeError("Connection lost"))
        client._conn = mock_conn
        client._session_id = "test-session-456"

        async def _test():
            await client.graceful_cancel()

        # Should not raise
        asyncio.run(_test())
