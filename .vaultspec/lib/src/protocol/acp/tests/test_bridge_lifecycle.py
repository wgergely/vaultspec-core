"""Lifecycle tests for ClaudeACPBridge.

Covers: constructor, on_connect, initialize, new_session, ext_method,
ext_notification, _extract_prompt_text, _convert_mcp_servers,
and full lifecycle unit tests (injected SDK via constructor DI).
"""

from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

import pytest
from tests.constants import TEST_PROJECT

from protocol.acp.claude_bridge import (
    ClaudeACPBridge,
    _convert_mcp_servers,
    _extract_prompt_text,
)
from protocol.providers.base import ClaudeModels

from .conftest import make_di_bridge, make_test_client, make_test_conn

pytestmark = [pytest.mark.unit]


class TestConstructor:
    """Test ClaudeACPBridge constructor and defaults."""

    def test_default_model(self):
        """Default model is ClaudeModels.MEDIUM."""
        bridge = ClaudeACPBridge()
        assert bridge._model == ClaudeModels.MEDIUM

    def test_custom_model(self):
        """Custom model is stored."""
        bridge = ClaudeACPBridge(model=ClaudeModels.HIGH)
        assert bridge._model == ClaudeModels.HIGH

    def test_debug_default_false(self):
        """Debug defaults to False."""
        bridge = ClaudeACPBridge()
        assert bridge._debug is False

    def test_debug_enabled(self):
        """Debug can be set to True."""
        bridge = ClaudeACPBridge(debug=True)
        assert bridge._debug is True

    def test_initial_state(self):
        """Constructor sets initial state correctly."""
        bridge = ClaudeACPBridge()
        assert bridge._conn is None
        assert bridge._sdk_client is None
        assert bridge._session_id is None
        assert bridge._pending_tools == {}
        assert bridge._cancelled is False

    def test_reads_mode(self):
        """Constructor reads mode via DI parameter."""
        bridge = ClaudeACPBridge(mode="read-only")
        assert bridge._mode == "read-only"

    def test_default_mode_read_write(self):
        """Default mode is read-write when no DI param provided."""
        bridge = ClaudeACPBridge()
        assert bridge._mode == "read-write"


class TestOnConnect:
    """Test the on_connect lifecycle method."""

    def test_stores_connection(self, bridge):
        """on_connect stores the connection for later use."""
        conn = make_test_conn()
        bridge.on_connect(conn)
        assert bridge._conn is conn

    def test_conn_starts_none(self, bridge):
        """Before on_connect, _conn is None."""
        assert bridge._conn is None


class TestInitialize:
    """Test the ACP initialize handshake."""

    @pytest.mark.asyncio
    async def test_returns_initialize_response(self, bridge):
        """initialize() returns an InitializeResponse with required fields."""
        from acp.schema import InitializeResponse

        result = await bridge.initialize(protocol_version=1)
        assert isinstance(result, InitializeResponse)

    @pytest.mark.asyncio
    async def test_protocol_version(self, bridge):
        """InitializeResponse includes protocol_version."""
        from acp import PROTOCOL_VERSION

        result = await bridge.initialize(protocol_version=1)
        assert result.protocol_version == PROTOCOL_VERSION

    @pytest.mark.asyncio
    async def test_agent_info(self, bridge):
        """InitializeResponse includes agent_info with name and version."""
        result = await bridge.initialize(protocol_version=1)
        assert result.agent_info.name == "claude-acp-bridge"
        assert result.agent_info.version == "0.1.0"

    @pytest.mark.asyncio
    async def test_agent_capabilities(self, bridge):
        """InitializeResponse includes agent_capabilities."""
        from acp.schema import AgentCapabilities

        result = await bridge.initialize(protocol_version=1)
        assert isinstance(result.agent_capabilities, AgentCapabilities)

    @pytest.mark.asyncio
    async def test_ignores_extra_kwargs(self, bridge):
        """initialize() accepts and ignores extra keyword arguments."""
        result = await bridge.initialize(
            protocol_version=1,
            client_capabilities=object(),
            client_info=object(),
            extra_field="ignored",
        )
        assert result.agent_info.name == "claude-acp-bridge"


class TestNewSession:
    """Test session creation via new_session()."""

    @pytest.mark.asyncio
    async def test_returns_new_session_response(self):
        """new_session() returns a NewSessionResponse with session_id."""
        from acp.schema import NewSessionResponse

        bridge, _holder, _captured = make_di_bridge()

        result = await bridge.new_session(cwd=str(TEST_PROJECT))
        assert isinstance(result, NewSessionResponse)
        assert isinstance(result.session_id, str)
        assert len(result.session_id) > 0

    @pytest.mark.asyncio
    async def test_session_id_is_uuid(self):
        """The session_id is a UUID-formatted string."""
        bridge, _holder, _captured = make_di_bridge()

        result = await bridge.new_session(cwd=str(TEST_PROJECT))
        # UUID format: 8-4-4-4-12 hex
        assert result.session_id.count("-") == 4

    @pytest.mark.asyncio
    async def test_passes_model(self):
        """The configured model is passed to ClaudeAgentOptions."""
        bridge, _holder, captured = make_di_bridge()

        await bridge.new_session(cwd=str(TEST_PROJECT))

        assert captured["model"] == ClaudeModels.MEDIUM

    @pytest.mark.asyncio
    async def test_passes_cwd(self):
        """The cwd parameter is passed to ClaudeAgentOptions."""
        bridge, _holder, captured = make_di_bridge()

        await bridge.new_session(cwd=str(TEST_PROJECT))

        assert captured["cwd"] == str(TEST_PROJECT)

    @pytest.mark.asyncio
    async def test_updates_root_dir(self):
        """new_session() updates the bridge's _root_dir from cwd."""
        bridge, _holder, _captured = make_di_bridge()

        await bridge.new_session(cwd=str(TEST_PROJECT))
        assert bridge._root_dir == str(TEST_PROJECT)

    @pytest.mark.asyncio
    async def test_passes_mcp_servers(self):
        """MCP server configs are converted and passed to options."""
        bridge, _holder, captured = make_di_bridge()

        mcp_servers = [
            {"name": "test-mcp", "command": "python", "args": ["-m", "server"]}
        ]

        await bridge.new_session(cwd=str(TEST_PROJECT), mcp_servers=mcp_servers)

        mcp = captured["mcp_servers"]
        assert isinstance(mcp, dict)
        assert "test-mcp" in mcp

    @pytest.mark.asyncio
    async def test_none_mcp_servers(self):
        """None mcp_servers results in empty dict."""
        bridge, _holder, captured = make_di_bridge()

        await bridge.new_session(cwd=str(TEST_PROJECT), mcp_servers=None)

        assert captured["mcp_servers"] == {}

    @pytest.mark.asyncio
    async def test_bypass_permissions(self):
        """Options include permission_mode=bypassPermissions."""
        bridge, _holder, captured = make_di_bridge()

        await bridge.new_session(cwd=str(TEST_PROJECT))

        assert captured["permission_mode"] == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_stores_sdk_client(self):
        """new_session() stores the SDK client on the bridge."""
        test_client = make_test_client()
        bridge, _holder, _captured = make_di_bridge(client=test_client)

        await bridge.new_session(cwd=str(TEST_PROJECT))
        assert bridge._sdk_client is test_client

    @pytest.mark.asyncio
    async def test_stores_session_id(self):
        """new_session() stores the session_id on the bridge."""
        bridge, _holder, _captured = make_di_bridge()

        result = await bridge.new_session(cwd=str(TEST_PROJECT))
        assert bridge._session_id == result.session_id

    @pytest.mark.asyncio
    async def test_sandbox_callback_read_only(self):
        """In read-only mode, options include a can_use_tool callback."""
        bridge_ro, _holder, captured = make_di_bridge(mode="read-only")
        await bridge_ro.new_session(cwd=str(TEST_PROJECT))

        assert captured["can_use_tool"] is not None

    @pytest.mark.asyncio
    async def test_no_sandbox_read_write(self):
        """In read-write mode, can_use_tool is None."""
        bridge_rw, _holder, captured = make_di_bridge(mode="read-write")
        await bridge_rw.new_session(cwd=str(TEST_PROJECT))

        assert captured["can_use_tool"] is None

    @pytest.mark.asyncio
    async def test_include_partial_messages(self):
        """new_session() passes include_partial_messages=True for delta streaming."""
        bridge, _holder, captured = make_di_bridge()

        await bridge.new_session(cwd=str(TEST_PROJECT))

        assert captured["include_partial_messages"] is True


class TestExtMethod:
    """Test the ext_method stub."""

    @pytest.mark.asyncio
    async def test_returns_empty_dict(self, bridge):
        """ext_method returns an empty dict."""
        result = await bridge.ext_method("custom/method", {"key": "value"})
        assert result == {}

    @pytest.mark.asyncio
    async def test_debug_logs(self, bridge_debug):
        """ext_method logs in debug mode (does not raise)."""
        result = await bridge_debug.ext_method("custom/method", {})
        assert result == {}


class TestExtNotification:
    """Test the ext_notification stub."""

    @pytest.mark.asyncio
    async def test_returns_none(self, bridge):
        """ext_notification returns None."""
        result = await bridge.ext_notification("custom/event", {"data": 1})
        assert result is None


class TestExtractPromptText:
    """Test the _extract_prompt_text module-level function."""

    def test_text_content_blocks(self):
        """TextContentBlock instances have their text extracted."""
        from acp.schema import TextContentBlock

        blocks = [
            TextContentBlock(type="text", text="First line"),
            TextContentBlock(type="text", text="Second line"),
        ]
        result = _extract_prompt_text(blocks)
        assert result == "First line\nSecond line"

    def test_single_block(self):
        """Single block returns its text directly."""
        from acp.schema import TextContentBlock

        blocks = [TextContentBlock(type="text", text="Hello")]
        assert _extract_prompt_text(blocks) == "Hello"

    def test_empty_list(self):
        """Empty list returns empty string."""
        assert _extract_prompt_text([]) == ""

    def test_non_text_block_with_text_attr(self):
        """Non-TextContentBlock with .text attribute is handled."""
        block = SimpleNamespace(text="fallback text")
        result = _extract_prompt_text([block])  # type: ignore[list-item]
        assert "fallback text" in result


class TestMCPServerConfigConversion:
    """Test ACP McpServerStdio -> SDK McpStdioServerConfig conversion."""

    def test_basic_dict_conversion(self):
        """Single dict server with all fields converts correctly."""
        acp_servers = [
            {
                "name": "vaultspec-mcp",
                "command": "python",
                "args": ["-m", "dispatch_server.server"],
                "env": {"ROOT_DIR": "/workspace"},
            }
        ]
        result = _convert_mcp_servers(acp_servers)

        assert "vaultspec-mcp" in result
        cfg = result["vaultspec-mcp"]
        assert cfg["command"] == "python"
        assert cfg["args"] == ["-m", "dispatch_server.server"]
        assert cfg["env"]["ROOT_DIR"] == "/workspace"

    def test_pydantic_model_conversion(self):
        """Pydantic model with model_dump() is handled."""
        model = SimpleNamespace()
        model.model_dump = lambda: {
            "name": "pydantic-mcp",
            "command": "node",
            "args": ["serve.js"],
        }

        result = _convert_mcp_servers([model])
        assert "pydantic-mcp" in result
        assert result["pydantic-mcp"]["command"] == "node"

    def test_multiple_servers(self):
        """Multiple servers convert to a dict keyed by name."""
        acp_servers = [
            {"name": "server-a", "command": "node", "args": ["a.js"]},
            {"name": "server-b", "command": "python", "args": ["b.py"]},
        ]
        result = _convert_mcp_servers(acp_servers)

        assert len(result) == 2
        assert result["server-a"]["command"] == "node"
        assert result["server-b"]["command"] == "python"

    def test_missing_name_uses_command(self):
        """If name is missing, the command is used as the key."""
        result = _convert_mcp_servers([{"command": "my-tool", "args": ["--serve"]}])
        assert "my-tool" in result

    def test_missing_optional_fields_omitted(self):
        """Missing args and env are NOT included (conditional inclusion)."""
        result = _convert_mcp_servers([{"name": "minimal", "command": "tool"}])
        cfg = result["minimal"]
        assert cfg["command"] == "tool"
        assert "args" not in cfg
        assert "env" not in cfg

    def test_empty_server_list(self):
        """Empty input returns empty dict."""
        assert _convert_mcp_servers([]) == {}

    def test_missing_command_skipped(self):
        """Server entries without a command are skipped."""
        result = _convert_mcp_servers([{"name": "no-cmd"}])
        assert result == {}

    def test_non_dict_non_model_skipped(self):
        """Non-dict, non-model entries are skipped."""
        result = _convert_mcp_servers(["not-a-server", 42])
        assert result == {}


class TestBridgeLifecycleUnit:
    """Full bridge lifecycle with injected SDK (no subprocess).

    Moved from test_e2e_bridge.py -- these are unit tests, not e2e.
    """

    @pytest.mark.asyncio
    async def test_initialize_then_session(self):
        """Full initialize -> new_session lifecycle with injected SDK."""
        bridge, _holder, _captured = make_di_bridge()

        # Step 1: initialize
        init_result = await bridge.initialize(protocol_version=1)
        assert init_result.agent_info.name == "claude-acp-bridge"

        # Step 2: new_session
        session_result = await bridge.new_session(cwd=str(TEST_PROJECT))
        assert isinstance(session_result.session_id, str)
        assert len(session_result.session_id) > 0
        assert bridge._sdk_client is not None

    @pytest.mark.asyncio
    async def test_cancel(self):
        """cancel() interrupts the SDK client."""
        test_client = make_test_client()
        bridge, _holder, _captured = make_di_bridge(client=test_client)

        # Create session first
        await bridge.new_session(cwd=str(TEST_PROJECT))
        assert bridge._sdk_client is test_client

        # Cancel
        await bridge.cancel(session_id=bridge._session_id)
        assert test_client.interrupt_count == 1
        assert bridge._cancelled is True

    def test_provider_prepares_bridge_command(self):
        """ClaudeProvider.prepare_process() returns correct bridge spawn command."""
        from protocol.providers.claude import ClaudeProvider

        provider = ClaudeProvider()
        spec = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"tier": "MEDIUM"},
            agent_persona="You are a test agent.",
            task_context="Do something useful.",
            root_dir=TEST_PROJECT,
        )

        assert spec.executable == sys.executable
        assert "-m" in spec.args
        assert "protocol.acp.claude_bridge" in spec.args
        assert "--model" in spec.args
        assert spec.env.get("VAULTSPEC_ROOT_DIR") == str(TEST_PROJECT)
        assert "CLAUDECODE" not in spec.env

    @pytest.mark.asyncio
    async def test_run_subagent_with_provider(self, tmp_path):
        """run_subagent() accepts a provider_instance and uses it."""
        from protocol.providers.claude import ClaudeProvider

        # Create minimal agent file
        agents_dir = tmp_path / ".vaultspec" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "test-agent.md").write_text(
            "---\ntier: MEDIUM\nmode: read-write\n---\nYou are a test agent.",
            encoding="utf-8",
        )

        provider = ClaudeProvider()
        spec = provider.prepare_process(
            agent_name="test-agent",
            agent_meta={"tier": "MEDIUM", "mode": "read-write"},
            agent_persona="You are a test agent.",
            task_context="Do something.",
            root_dir=tmp_path,
        )

        # Verify the ProcessSpec is well-formed
        from protocol.providers.base import ProcessSpec

        assert isinstance(spec, ProcessSpec)
        assert spec.initial_prompt_override == "Do something."
        assert spec.env.get("VAULTSPEC_SYSTEM_PROMPT")


class TestSetSessionModel:
    """Test set_session_model updates the bridge model."""

    @pytest.mark.asyncio
    async def test_updates_model(self, bridge):
        """set_session_model updates bridge._model."""
        assert bridge._model == ClaudeModels.MEDIUM
        await bridge.set_session_model(model_id=ClaudeModels.HIGH, session_id="s1")
        assert bridge._model == ClaudeModels.HIGH

    @pytest.mark.asyncio
    async def test_updates_sdk_options(self):
        """set_session_model updates SDK client options.model in active session."""
        test_client = make_test_client()
        test_client._options = SimpleNamespace(model=ClaudeModels.MEDIUM)
        bridge, _holder, _captured = make_di_bridge(client=test_client)

        await bridge.new_session(cwd=str(TEST_PROJECT))
        await bridge.set_session_model(model_id=ClaudeModels.HIGH, session_id="s1")

        assert bridge._model == ClaudeModels.HIGH
        assert test_client._options.model == ClaudeModels.HIGH

    @pytest.mark.asyncio
    async def test_no_session_still_updates_model(self, bridge):
        """set_session_model works even without an active session."""
        assert bridge._sdk_client is None
        await bridge.set_session_model(model_id=ClaudeModels.LOW, session_id="s1")
        assert bridge._model == ClaudeModels.LOW

    @pytest.mark.asyncio
    async def test_no_options_attr_no_crash(self):
        """set_session_model handles SDK client without _options attribute."""
        test_client = make_test_client()
        # Deliberately no _options attr (getattr returns None)
        if hasattr(test_client, "_options"):
            del test_client._options
        bridge, _holder, _captured = make_di_bridge(client=test_client)

        await bridge.new_session(cwd=str(TEST_PROJECT))
        # Should not raise
        await bridge.set_session_model(model_id=ClaudeModels.HIGH, session_id="s1")
        assert bridge._model == ClaudeModels.HIGH

    @pytest.mark.asyncio
    async def test_returns_none(self, bridge):
        """set_session_model returns None (router normalizes to response)."""
        result = await bridge.set_session_model(
            model_id=ClaudeModels.HIGH, session_id="s1"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_debug_logs(self, bridge_debug):
        """set_session_model logs in debug mode."""
        # Should not raise
        await bridge_debug.set_session_model(
            model_id=ClaudeModels.HIGH, session_id="s1"
        )
        assert bridge_debug._model == ClaudeModels.HIGH


class TestSetSessionMode:
    """Test set_session_mode updates the bridge sandboxing mode."""

    @pytest.mark.asyncio
    async def test_updates_mode(self, bridge):
        """set_session_mode updates bridge._mode."""
        assert bridge._mode == "read-write"
        await bridge.set_session_mode(mode_id="read-only", session_id="s1")
        assert bridge._mode == "read-only"

    @pytest.mark.asyncio
    async def test_switch_to_read_write(self):
        """set_session_mode can switch from read-only to read-write."""
        ro_bridge = ClaudeACPBridge(mode="read-only")
        assert ro_bridge._mode == "read-only"

        await ro_bridge.set_session_mode(mode_id="read-write", session_id="s1")
        assert ro_bridge._mode == "read-write"

    @pytest.mark.asyncio
    async def test_updates_sandbox_callback_to_read_only(self):
        """Switching to read-only mode installs a sandbox callback."""
        test_client = make_test_client()
        test_client._options = SimpleNamespace(can_use_tool=None)
        bridge, _holder, _captured = make_di_bridge(client=test_client)

        await bridge.new_session(cwd=str(TEST_PROJECT))
        assert test_client._options.can_use_tool is None

        await bridge.set_session_mode(mode_id="read-only", session_id="s1")
        assert bridge._mode == "read-only"
        assert test_client._options.can_use_tool is not None

    @pytest.mark.asyncio
    async def test_updates_sandbox_callback_to_read_write(self):
        """Switching to read-write mode removes the sandbox callback."""
        test_client = make_test_client()
        test_client._options = SimpleNamespace(can_use_tool=None)
        bridge, _holder, _captured = make_di_bridge(
            client=test_client, mode="read-only"
        )
        bridge.on_connect(make_test_conn())

        await bridge.new_session(cwd=str(TEST_PROJECT))
        # set_session_mode to read-only installs the callback
        await bridge.set_session_mode(mode_id="read-only", session_id="s1")
        assert test_client._options.can_use_tool is not None

        await bridge.set_session_mode(mode_id="read-write", session_id="s1")
        assert bridge._mode == "read-write"
        assert test_client._options.can_use_tool is None

    @pytest.mark.asyncio
    async def test_no_session_still_updates_mode(self, bridge):
        """set_session_mode works even without an active session."""
        assert bridge._sdk_client is None
        await bridge.set_session_mode(mode_id="read-only", session_id="s1")
        assert bridge._mode == "read-only"

    @pytest.mark.asyncio
    async def test_no_options_attr_no_crash(self):
        """set_session_mode handles SDK client without _options attribute."""
        test_client = make_test_client()
        if hasattr(test_client, "_options"):
            del test_client._options
        bridge, _holder, _captured = make_di_bridge(client=test_client)

        await bridge.new_session(cwd=str(TEST_PROJECT))
        await bridge.set_session_mode(mode_id="read-only", session_id="s1")
        assert bridge._mode == "read-only"

    @pytest.mark.asyncio
    async def test_returns_none(self, bridge):
        """set_session_mode returns None (router normalizes to response)."""
        result = await bridge.set_session_mode(mode_id="read-only", session_id="s1")
        assert result is None

    @pytest.mark.asyncio
    async def test_debug_logs(self, bridge_debug):
        """set_session_mode logs in debug mode."""
        await bridge_debug.set_session_mode(mode_id="read-only", session_id="s1")
        assert bridge_debug._mode == "read-only"


class TestAuthenticate:
    """Test authenticate returns AuthenticateResponse."""

    @pytest.mark.asyncio
    async def test_returns_authenticate_response(self, bridge):
        """authenticate returns an AuthenticateResponse instance (not None)."""
        from acp.schema import AuthenticateResponse

        result = await bridge.authenticate(method_id="api-key")
        assert result is not None
        assert isinstance(result, AuthenticateResponse)

    @pytest.mark.asyncio
    async def test_accepts_any_method_id(self, bridge):
        """authenticate works with any method_id string."""
        from acp.schema import AuthenticateResponse

        for method_id in ["api-key", "oauth", "bearer-token", ""]:
            result = await bridge.authenticate(method_id=method_id)
            assert isinstance(result, AuthenticateResponse)

    @pytest.mark.asyncio
    async def test_accepts_extra_kwargs(self, bridge):
        """authenticate accepts and ignores extra kwargs."""
        from acp.schema import AuthenticateResponse

        result = await bridge.authenticate(
            method_id="api-key",
            credentials={"token": "secret"},
            extra="ignored",
        )
        assert isinstance(result, AuthenticateResponse)

    @pytest.mark.asyncio
    async def test_debug_logs_sdk_auth(self, bridge_debug, caplog):
        """authenticate in debug mode logs SDK auth readiness."""
        with caplog.at_level(logging.DEBUG, logger="protocol.acp.claude_bridge"):
            await bridge_debug.authenticate(method_id="api-key")

        assert any("SDK handles auth internally" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_does_not_affect_bridge_state(self, bridge):
        """authenticate does not modify any bridge internal state."""
        original_model = bridge._model
        original_mode = bridge._mode
        original_conn = bridge._conn
        original_client = bridge._sdk_client
        original_session = bridge._session_id

        await bridge.authenticate(method_id="api-key")

        assert bridge._model == original_model
        assert bridge._mode == original_mode
        assert bridge._conn is original_conn
        assert bridge._sdk_client is original_client
        assert bridge._session_id is original_session


class TestListSessions:
    """Test list_sessions returns session state from tracked sessions."""

    @pytest.mark.asyncio
    async def test_empty_before_any_session(self, bridge):
        """list_sessions returns empty sessions list with no sessions created."""
        from acp.schema import ListSessionsResponse

        result = await bridge.list_sessions()
        assert isinstance(result, ListSessionsResponse)
        assert result.sessions == []

    @pytest.mark.asyncio
    async def test_returns_session_info_after_new_session(self):
        """list_sessions returns SessionInfo after new_session creates one."""
        from acp.schema import ListSessionsResponse, SessionInfo

        bridge, _holder, _captured = make_di_bridge()
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        result = await bridge.list_sessions()
        assert isinstance(result, ListSessionsResponse)
        assert len(result.sessions) == 1

        info = result.sessions[0]
        assert isinstance(info, SessionInfo)
        assert info.session_id == session_id
        assert info.cwd == str(TEST_PROJECT)
        assert info.title == f"{ClaudeModels.MEDIUM} (read-write)"
        assert info.updated_at is not None

    @pytest.mark.asyncio
    async def test_cwd_filter(self):
        """list_sessions filters sessions by cwd when specified."""
        bridge, _holder, _captured = make_di_bridge()

        dir_a = str(TEST_PROJECT / "workspace-a")
        dir_b = str(TEST_PROJECT / "workspace-b")
        await bridge.new_session(cwd=dir_a)
        await bridge.new_session(cwd=dir_b)

        # Filter to only workspace-a
        result = await bridge.list_sessions(cwd=dir_a)
        assert len(result.sessions) == 1
        assert result.sessions[0].cwd == dir_a

        # Filter to workspace-b
        result = await bridge.list_sessions(cwd=dir_b)
        assert len(result.sessions) == 1
        assert result.sessions[0].cwd == dir_b

        # No filter returns all
        result = await bridge.list_sessions()
        assert len(result.sessions) == 2

    @pytest.mark.asyncio
    async def test_multiple_sessions(self):
        """list_sessions returns all tracked sessions."""
        bridge, _holder, _captured = make_di_bridge()

        dir1 = str(TEST_PROJECT / "ws1")
        dir2 = str(TEST_PROJECT / "ws2")
        dir3 = str(TEST_PROJECT / "ws3")
        await bridge.new_session(cwd=dir1)
        await bridge.new_session(cwd=dir2)
        await bridge.new_session(cwd=dir3)

        result = await bridge.list_sessions()
        assert len(result.sessions) == 3
        cwds = {s.cwd for s in result.sessions}
        assert cwds == {dir1, dir2, dir3}

    @pytest.mark.asyncio
    async def test_cwd_filter_no_match(self):
        """list_sessions with non-matching cwd returns empty list."""
        bridge, _holder, _captured = make_di_bridge()
        await bridge.new_session(cwd=str(TEST_PROJECT))

        result = await bridge.list_sessions(cwd=str(TEST_PROJECT / "nonexistent"))
        assert result.sessions == []


class TestLoadSession:
    """Test load_session reconnects SDK from stored state."""

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_session(self, bridge):
        """load_session returns None for a session_id not in _sessions."""
        result = await bridge.load_session(
            cwd=str(TEST_PROJECT), session_id="nonexistent"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_loads_existing_session(self):
        """load_session returns LoadSessionResponse for a known session."""
        from acp.schema import LoadSessionResponse

        bridge, holder, _captured = make_di_bridge()
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        # Swap to a fresh client for the load reconnection
        holder.client = make_test_client()

        result = await bridge.load_session(cwd=str(TEST_PROJECT), session_id=session_id)
        assert result is not None
        assert isinstance(result, LoadSessionResponse)

    @pytest.mark.asyncio
    async def test_disconnects_previous_client(self):
        """load_session disconnects the previous SDK client before reconnecting."""
        original_client = make_test_client()
        bridge, holder, _captured = make_di_bridge(client=original_client)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        # Reset disconnect tracking, then load
        original_client.disconnect_count = 0
        new_client = make_test_client()
        holder.client = new_client

        await bridge.load_session(cwd=str(TEST_PROJECT), session_id=session_id)

        assert original_client.disconnect_count == 1
        assert len(new_client.connect_calls) == 1

    @pytest.mark.asyncio
    async def test_config_preserved_from_stored_state(self):
        """load_session rebuilds SDK client with model/mode from stored state."""
        bridge, holder, _captured = make_di_bridge()
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        # Mutate bridge-level model to prove load restores from stored state
        bridge._model = ClaudeModels.HIGH

        holder.client = make_test_client()

        new_cwd = str(TEST_PROJECT / "new-cwd")
        await bridge.load_session(cwd=new_cwd, session_id=session_id)

        # Bridge model should be restored from stored state, not the mutated value
        assert bridge._model == ClaudeModels.MEDIUM
        assert bridge._session_id == session_id
        assert bridge._root_dir == new_cwd

    @pytest.mark.asyncio
    async def test_marks_session_connected(self):
        """load_session sets the session state back to connected=True."""
        bridge, holder, _captured = make_di_bridge()
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        # Mark disconnected (as cancel would do)
        bridge._sessions[session_id].connected = False

        holder.client = make_test_client()

        await bridge.load_session(cwd=str(TEST_PROJECT), session_id=session_id)
        assert bridge._sessions[session_id].connected is True


class TestResumeSession:
    """Test resume_session reconnects SDK from stored state."""

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_session(self, bridge):
        """resume_session returns None for a session_id not in _sessions."""
        result = await bridge.resume_session(
            cwd=str(TEST_PROJECT), session_id="unknown"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_resumes_existing_session(self):
        """resume_session returns ResumeSessionResponse for a known session."""
        from acp.schema import ResumeSessionResponse

        bridge, holder, _captured = make_di_bridge()
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        holder.client = make_test_client()

        result = await bridge.resume_session(
            cwd=str(TEST_PROJECT), session_id=session_id
        )
        assert result is not None
        assert isinstance(result, ResumeSessionResponse)

    @pytest.mark.asyncio
    async def test_disconnects_previous_client(self):
        """resume_session disconnects the previous SDK client."""
        original_client = make_test_client()
        bridge, holder, _captured = make_di_bridge(client=original_client)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        original_client.disconnect_count = 0
        new_client = make_test_client()
        holder.client = new_client

        await bridge.resume_session(cwd=str(TEST_PROJECT), session_id=session_id)

        assert original_client.disconnect_count == 1
        assert len(new_client.connect_calls) == 1

    @pytest.mark.asyncio
    async def test_config_preserved_from_stored_state(self):
        """resume_session rebuilds SDK client with config from stored state."""
        bridge, holder, _captured = make_di_bridge()
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        # Mutate bridge-level model
        bridge._model = ClaudeModels.HIGH

        holder.client = make_test_client()

        new_cwd = str(TEST_PROJECT / "new-cwd")
        await bridge.resume_session(cwd=new_cwd, session_id=session_id)

        # Bridge model restored from stored state
        assert bridge._model == ClaudeModels.MEDIUM
        assert bridge._session_id == session_id
        assert bridge._root_dir == new_cwd

    @pytest.mark.asyncio
    async def test_marks_session_connected(self):
        """resume_session sets the session state back to connected=True."""
        bridge, holder, _captured = make_di_bridge()
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        bridge._sessions[session_id].connected = False

        holder.client = make_test_client()

        await bridge.resume_session(cwd=str(TEST_PROJECT), session_id=session_id)
        assert bridge._sessions[session_id].connected is True


class TestForkSession:
    """Test fork_session creates a new session from an existing one."""

    @pytest.mark.asyncio
    async def test_raises_for_unknown_session(self, bridge):
        """fork_session raises RuntimeError for a session_id not in _sessions."""
        with pytest.raises(RuntimeError, match=r"Cannot fork.*not found"):
            await bridge.fork_session(cwd=str(TEST_PROJECT), session_id="nonexistent")

    @pytest.mark.asyncio
    async def test_returns_fork_response_with_new_id(self):
        """fork_session returns ForkSessionResponse with a new session_id."""
        from acp.schema import ForkSessionResponse

        bridge, holder, _captured = make_di_bridge()
        await bridge.new_session(cwd=str(TEST_PROJECT))
        source_id = bridge._session_id

        new_client = make_test_client()
        holder.client = new_client

        result = await bridge.fork_session(cwd=str(TEST_PROJECT), session_id=source_id)
        assert isinstance(result, ForkSessionResponse)
        # The new session_id must differ from the source
        assert result.session_id != source_id
        assert result.session_id is not None

    @pytest.mark.asyncio
    async def test_clones_config_from_source(self):
        """fork_session clones model and mode from the source session."""
        bridge, holder, _captured = make_di_bridge()
        await bridge.new_session(cwd=str(TEST_PROJECT))
        source_id = bridge._session_id

        holder.client = make_test_client()

        fork_cwd = str(TEST_PROJECT / "fork-cwd")
        result = await bridge.fork_session(cwd=fork_cwd, session_id=source_id)
        new_id = result.session_id

        # Verify the forked session has the source's model and mode
        forked_state = bridge._sessions[new_id]
        source_state = bridge._sessions[source_id]
        assert forked_state.model == source_state.model
        assert forked_state.mode == source_state.mode
        assert forked_state.cwd == fork_cwd

    @pytest.mark.asyncio
    async def test_new_session_tracked(self):
        """fork_session stores the new session in self._sessions."""
        bridge, holder, _captured = make_di_bridge()
        await bridge.new_session(cwd=str(TEST_PROJECT))
        source_id = bridge._session_id

        holder.client = make_test_client()

        result = await bridge.fork_session(cwd=str(TEST_PROJECT), session_id=source_id)
        new_id = result.session_id

        assert new_id in bridge._sessions
        assert bridge._sessions[new_id].session_id == new_id
        assert bridge._sessions[new_id].connected is True
        # Source session should still exist
        assert source_id in bridge._sessions

    @pytest.mark.asyncio
    async def test_disconnects_previous_client(self):
        """fork_session disconnects the current SDK client before forking."""
        original_client = make_test_client()
        bridge, holder, _captured = make_di_bridge(client=original_client)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        source_id = bridge._session_id

        original_client.disconnect_count = 0
        new_client = make_test_client()
        holder.client = new_client

        await bridge.fork_session(cwd=str(TEST_PROJECT), session_id=source_id)

        assert original_client.disconnect_count == 1
        assert len(new_client.connect_calls) == 1

    @pytest.mark.asyncio
    async def test_bridge_state_updated_to_forked_session(self):
        """fork_session updates bridge._session_id to the new forked session."""
        bridge, holder, _captured = make_di_bridge()
        await bridge.new_session(cwd=str(TEST_PROJECT))
        source_id = bridge._session_id

        new_client = make_test_client()
        holder.client = new_client

        result = await bridge.fork_session(cwd=str(TEST_PROJECT), session_id=source_id)
        assert bridge._session_id == result.session_id
        assert bridge._sdk_client is new_client


class TestSessionTracking:
    """Test that new_session stores _SessionState and cancel marks disconnected."""

    @pytest.mark.asyncio
    async def test_new_session_stores_session_state(self):
        """new_session stores a _SessionState in self._sessions."""
        from protocol.acp.claude_bridge import _SessionState

        bridge, _holder, _captured = make_di_bridge()
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        assert session_id in bridge._sessions
        state = bridge._sessions[session_id]
        assert isinstance(state, _SessionState)
        assert state.session_id == session_id
        assert state.cwd == str(TEST_PROJECT)
        assert state.model == ClaudeModels.MEDIUM
        assert state.mode == "read-write"
        assert state.mcp_servers == []
        assert state.connected is True
        assert state.created_at is not None

    @pytest.mark.asyncio
    async def test_cancel_marks_session_disconnected(self):
        """cancel sets the session's connected flag to False."""
        bridge, _holder, _captured = make_di_bridge()
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        assert bridge._sessions[session_id].connected is True
        await bridge.cancel(session_id=session_id)
        assert bridge._sessions[session_id].connected is False

    @pytest.mark.asyncio
    async def test_multiple_sessions_tracked_independently(self):
        """Each new_session creates a separate _SessionState entry."""
        bridge, _holder, _captured = make_di_bridge()

        dir1 = str(TEST_PROJECT / "ws1")
        dir2 = str(TEST_PROJECT / "ws2")
        await bridge.new_session(cwd=dir1)
        id1 = bridge._session_id
        await bridge.new_session(cwd=dir2)
        id2 = bridge._session_id

        assert id1 != id2
        assert id1 in bridge._sessions
        assert id2 in bridge._sessions
        assert bridge._sessions[id1].cwd == dir1
        assert bridge._sessions[id2].cwd == dir2


class TestBridgeFeatureConfig:
    """Verify bridge reads DI constructor params.

    Wires them to ClaudeAgentOptions.
    """

    def test_max_turns_from_di(self):
        bridge = ClaudeACPBridge(max_turns=10)
        assert bridge._max_turns == 10

    def test_budget_from_di(self):
        bridge = ClaudeACPBridge(budget_usd=2.5)
        assert bridge._budget_usd == 2.5

    def test_allowed_tools_from_di(self):
        bridge = ClaudeACPBridge(allowed_tools=["Glob", "Read", "Grep"])
        assert bridge._allowed_tools == ["Glob", "Read", "Grep"]

    def test_disallowed_tools_from_di(self):
        bridge = ClaudeACPBridge(disallowed_tools=["Bash", "Write"])
        assert bridge._disallowed_tools == ["Bash", "Write"]

    def test_effort_from_di(self):
        bridge = ClaudeACPBridge(effort="high")
        assert bridge._effort == "high"

    def test_fallback_model_from_di(self):
        bridge = ClaudeACPBridge(fallback_model=ClaudeModels.LOW)
        assert bridge._fallback_model == ClaudeModels.LOW

    def test_include_dirs_from_di(self):
        bridge = ClaudeACPBridge(include_dirs=[".vault", "src"])
        assert bridge._include_dirs == [".vault", "src"]

    def test_output_format_from_di(self):
        bridge = ClaudeACPBridge(output_format="json")
        assert bridge._output_format == "json"

    def test_defaults_when_no_di(self):
        """Without DI params, all feature fields default to None/empty."""
        bridge = ClaudeACPBridge()
        assert bridge._max_turns is None
        assert bridge._budget_usd is None
        assert bridge._allowed_tools == []
        assert bridge._disallowed_tools == []
        assert bridge._effort is None
        assert bridge._fallback_model is None
        assert bridge._include_dirs == []
        assert bridge._output_format is None

    def test_build_options_includes_features(self):
        """_build_options() passes features to ClaudeAgentOptions kwargs."""
        bridge, _holder, captured = make_di_bridge(
            max_turns=15,
            budget_usd=3.0,
            effort="max",
            fallback_model=ClaudeModels.LOW,
            allowed_tools=["Glob", "Read"],
            disallowed_tools=["Bash"],
            include_dirs=[".vault"],
        )
        bridge._build_options(str(TEST_PROJECT), {}, None)

        assert captured["max_turns"] == 15
        assert captured["max_budget_usd"] == 3.0
        assert captured["effort"] == "max"
        assert captured["fallback_model"] == ClaudeModels.LOW
        assert captured["allowed_tools"] == ["Glob", "Read"]
        assert captured["disallowed_tools"] == ["Bash"]
        assert captured["add_dirs"] == [".vault"]

    def test_build_options_omits_none_features(self):
        """_build_options() omits features that are None/empty."""
        bridge, _holder, captured = make_di_bridge()
        bridge._build_options(str(TEST_PROJECT), {}, None)

        assert "max_turns" not in captured
        assert "max_budget_usd" not in captured
        assert "effort" not in captured
        assert "fallback_model" not in captured
        assert "allowed_tools" not in captured
        assert "disallowed_tools" not in captured
        assert "add_dirs" not in captured
        assert "output_format" not in captured

    def test_output_format_json_passed_to_sdk(self):
        """_build_options() passes output_format dict when json."""
        bridge, _holder, captured = make_di_bridge(output_format="json")
        bridge._build_options(str(TEST_PROJECT), {}, None)

        assert captured["output_format"] == {
            "type": "json_object",
        }

    def test_output_format_text_not_passed(self):
        """_build_options() omits output_format for text."""
        bridge, _holder, captured = make_di_bridge(output_format="text")
        bridge._build_options(str(TEST_PROJECT), {}, None)

        assert "output_format" not in captured

    def test_system_prompt_uses_preset_with_append(self):
        """_build_options() wraps system_prompt in SystemPromptPreset dict."""
        bridge, _holder, captured = make_di_bridge(system_prompt="You are a helper.")
        bridge._build_options(str(TEST_PROJECT), {}, None)

        sp = captured["system_prompt"]
        assert isinstance(sp, dict)
        assert sp["type"] == "preset"
        assert sp["preset"] == "claude_code"
        assert sp["append"] == "You are a helper."

    def test_system_prompt_none_uses_preset_without_append(self):
        """_build_options() uses bare preset when system_prompt is falsy."""
        bridge, _holder, captured = make_di_bridge(system_prompt=None)
        bridge._build_options(str(TEST_PROJECT), {}, None)

        sp = captured["system_prompt"]
        assert isinstance(sp, dict)
        assert sp["type"] == "preset"
        assert sp["preset"] == "claude_code"
        assert "append" not in sp

    def test_system_prompt_empty_string_uses_preset_without_append(self):
        """_build_options() treats empty string as falsy — bare preset."""
        bridge, _holder, captured = make_di_bridge(system_prompt="")
        bridge._build_options(str(TEST_PROJECT), {}, None)

        sp = captured["system_prompt"]
        assert isinstance(sp, dict)
        assert sp["type"] == "preset"
        assert sp["preset"] == "claude_code"
        assert "append" not in sp
