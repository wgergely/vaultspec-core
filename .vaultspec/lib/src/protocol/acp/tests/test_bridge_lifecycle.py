"""Lifecycle tests for ClaudeACPBridge.

Covers: constructor, on_connect, initialize, new_session, ext_method,
ext_notification, _extract_prompt_text, _convert_mcp_servers,
and full lifecycle unit tests (mocked SDK).
"""

from __future__ import annotations

import logging
import sys
from typing import ClassVar

import pytest

from protocol.acp.claude_bridge import (
    ClaudeACPBridge,
    _convert_mcp_servers,
    _extract_prompt_text,
)

from .conftest import TEST_PROJECT, FakeNamespace, make_sdk_mock

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Module-level helpers for patching SDK classes
# ---------------------------------------------------------------------------


class _OptionsRecorder:
    """Records kwargs passed to ClaudeAgentOptions constructor."""

    last_call: ClassVar[dict[str, object]] = {}

    def __init__(self, **kwargs: object) -> None:
        _OptionsRecorder.last_call = kwargs

    @classmethod
    def reset(cls) -> None:
        cls.last_call = {}


class _SDKFactory:
    """Mutable factory for FakeSDKClient instances.

    Tests that need to swap the SDK client mid-test can set
    ``factory.client = new_mock`` between calls.
    """

    def __init__(self, client=None):
        self.client = client or make_sdk_mock()

    def __call__(self, *_args, **_kwargs):
        return self.client


def _patch_sdk(monkeypatch, mock_client=None):
    """Patch ClaudeSDKClient and ClaudeAgentOptions via monkeypatch.

    Returns a ``_SDKFactory`` whose ``.client`` attribute is the current
    FakeSDKClient.  For simple cases use ``factory.client`` to access the
    mock; to swap the client mid-test just assign ``factory.client = new_mock``.
    """
    factory = _SDKFactory(mock_client)
    monkeypatch.setattr(
        "protocol.acp.claude_bridge.ClaudeSDKClient",
        factory,
    )
    _OptionsRecorder.reset()
    monkeypatch.setattr(
        "protocol.acp.claude_bridge.ClaudeAgentOptions",
        _OptionsRecorder,
    )
    return factory


# ---------------------------------------------------------------------------
# TestConstructor
# ---------------------------------------------------------------------------


class TestConstructor:
    """Test ClaudeACPBridge constructor and defaults."""

    def test_default_model(self):
        """Default model is claude-sonnet-4-5."""
        bridge = ClaudeACPBridge()
        assert bridge._model == "claude-sonnet-4-5"

    def test_custom_model(self):
        """Custom model is stored."""
        bridge = ClaudeACPBridge(model="claude-opus-4-6")
        assert bridge._model == "claude-opus-4-6"

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

    def test_reads_env_mode(self, monkeypatch):
        """Constructor reads VS_AGENT_MODE from environment."""
        monkeypatch.setenv("VS_AGENT_MODE", "read-only")
        bridge = ClaudeACPBridge()
        assert bridge._mode == "read-only"

    def test_default_mode_read_write(self, monkeypatch):
        """Default mode is read-write when env var not set."""
        monkeypatch.delenv("VS_AGENT_MODE", raising=False)
        bridge = ClaudeACPBridge()
        assert bridge._mode == "read-write"


# ---------------------------------------------------------------------------
# TestOnConnect
# ---------------------------------------------------------------------------


class TestOnConnect:
    """Test the on_connect lifecycle method."""

    def test_stores_connection(self, bridge, mock_conn):
        """on_connect stores the connection for later use."""
        bridge.on_connect(mock_conn)
        assert bridge._conn is mock_conn

    def test_conn_starts_none(self, bridge):
        """Before on_connect, _conn is None."""
        assert bridge._conn is None


# ---------------------------------------------------------------------------
# TestInitialize
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# TestNewSession
# ---------------------------------------------------------------------------


class TestNewSession:
    """Test session creation via new_session()."""

    @pytest.mark.asyncio
    async def test_returns_new_session_response(self, bridge, monkeypatch):
        """new_session() returns a NewSessionResponse with session_id."""
        from acp.schema import NewSessionResponse

        _patch_sdk(monkeypatch)

        result = await bridge.new_session(cwd=str(TEST_PROJECT))
        assert isinstance(result, NewSessionResponse)
        assert isinstance(result.session_id, str)
        assert len(result.session_id) > 0

    @pytest.mark.asyncio
    async def test_session_id_is_uuid(self, bridge, monkeypatch):
        """The session_id is a UUID-formatted string."""
        _patch_sdk(monkeypatch)

        result = await bridge.new_session(cwd=str(TEST_PROJECT))
        # UUID format: 8-4-4-4-12 hex
        assert result.session_id.count("-") == 4

    @pytest.mark.asyncio
    async def test_passes_model(self, bridge, monkeypatch):
        """The configured model is passed to ClaudeAgentOptions."""
        _patch_sdk(monkeypatch)

        await bridge.new_session(cwd=str(TEST_PROJECT))

        assert _OptionsRecorder.last_call["model"] == "claude-sonnet-4-5"

    @pytest.mark.asyncio
    async def test_passes_cwd(self, bridge, monkeypatch):
        """The cwd parameter is passed to ClaudeAgentOptions."""
        _patch_sdk(monkeypatch)

        await bridge.new_session(cwd=str(TEST_PROJECT))

        assert _OptionsRecorder.last_call["cwd"] == str(TEST_PROJECT)

    @pytest.mark.asyncio
    async def test_updates_root_dir(self, bridge, monkeypatch):
        """new_session() updates the bridge's _root_dir from cwd."""
        _patch_sdk(monkeypatch)

        await bridge.new_session(cwd=str(TEST_PROJECT))
        assert bridge._root_dir == str(TEST_PROJECT)

    @pytest.mark.asyncio
    async def test_passes_mcp_servers(self, bridge, monkeypatch):
        """MCP server configs are converted and passed to options."""
        _patch_sdk(monkeypatch)

        mcp_servers = [
            FakeNamespace(
                name="test-mcp",
                command="python",
                args=["-m", "server"],
            )
        ]

        await bridge.new_session(cwd=str(TEST_PROJECT), mcp_servers=mcp_servers)

        mcp = _OptionsRecorder.last_call["mcp_servers"]
        assert isinstance(mcp, dict)
        assert "test-mcp" in mcp

    @pytest.mark.asyncio
    async def test_none_mcp_servers(self, bridge, monkeypatch):
        """None mcp_servers results in empty dict."""
        _patch_sdk(monkeypatch)

        await bridge.new_session(cwd=str(TEST_PROJECT), mcp_servers=None)

        assert _OptionsRecorder.last_call["mcp_servers"] == {}

    @pytest.mark.asyncio
    async def test_bypass_permissions(self, bridge, monkeypatch):
        """Options include permission_mode=bypassPermissions."""
        _patch_sdk(monkeypatch)

        await bridge.new_session(cwd=str(TEST_PROJECT))

        assert _OptionsRecorder.last_call["permission_mode"] == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_stores_sdk_client(self, bridge, monkeypatch):
        """new_session() stores the SDK client on the bridge."""
        mock_instance = make_sdk_mock()
        _patch_sdk(monkeypatch, mock_client=mock_instance)

        await bridge.new_session(cwd=str(TEST_PROJECT))
        assert bridge._sdk_client is mock_instance

    @pytest.mark.asyncio
    async def test_stores_session_id(self, bridge, monkeypatch):
        """new_session() stores the session_id on the bridge."""
        _patch_sdk(monkeypatch)

        result = await bridge.new_session(cwd=str(TEST_PROJECT))
        assert bridge._session_id == result.session_id

    @pytest.mark.asyncio
    async def test_sandbox_callback_read_only(self, monkeypatch):
        """In read-only mode, options include a can_use_tool callback."""
        _patch_sdk(monkeypatch)

        monkeypatch.setenv("VS_AGENT_MODE", "read-only")
        bridge_ro = ClaudeACPBridge(model="claude-sonnet-4-5")
        await bridge_ro.new_session(cwd=str(TEST_PROJECT))

        assert _OptionsRecorder.last_call["can_use_tool"] is not None

    @pytest.mark.asyncio
    async def test_no_sandbox_read_write(self, monkeypatch):
        """In read-write mode, can_use_tool is None."""
        _patch_sdk(monkeypatch)

        monkeypatch.setenv("VS_AGENT_MODE", "read-write")
        bridge_rw = ClaudeACPBridge(model="claude-sonnet-4-5")
        await bridge_rw.new_session(cwd=str(TEST_PROJECT))

        assert _OptionsRecorder.last_call["can_use_tool"] is None

    @pytest.mark.asyncio
    async def test_include_partial_messages(self, bridge, monkeypatch):
        """new_session() passes include_partial_messages=True for delta streaming."""
        _patch_sdk(monkeypatch)

        await bridge.new_session(cwd=str(TEST_PROJECT))

        assert _OptionsRecorder.last_call["include_partial_messages"] is True


# ---------------------------------------------------------------------------
# TestExtMethod / TestExtNotification
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# TestExtractPromptText
# ---------------------------------------------------------------------------


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

        class FakeBlock:
            text = "fallback text"

        result = _extract_prompt_text([FakeBlock()])  # type: ignore[list-item]
        assert "fallback text" in result


# ---------------------------------------------------------------------------
# TestMCPServerConfigConversion
# ---------------------------------------------------------------------------


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

        class FakePydanticModel:
            def model_dump(self):
                return {
                    "name": "pydantic-mcp",
                    "command": "node",
                    "args": ["serve.js"],
                }

        result = _convert_mcp_servers([FakePydanticModel()])
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


# ---------------------------------------------------------------------------
# TestBridgeLifecycleUnit
# ---------------------------------------------------------------------------


class TestBridgeLifecycleUnit:
    """Full bridge lifecycle with mocked SDK (no subprocess).

    Moved from test_e2e_bridge.py — these are unit tests, not e2e.
    """

    @pytest.mark.asyncio
    async def test_initialize_then_session_mocked(self, bridge, monkeypatch):
        """Full initialize -> new_session lifecycle with mocked SDK."""
        _patch_sdk(monkeypatch)

        # Step 1: initialize
        init_result = await bridge.initialize(protocol_version=1)
        assert init_result.agent_info.name == "claude-acp-bridge"

        # Step 2: new_session
        session_result = await bridge.new_session(cwd=str(TEST_PROJECT))
        assert isinstance(session_result.session_id, str)
        assert len(session_result.session_id) > 0
        assert bridge._sdk_client is not None

    @pytest.mark.asyncio
    async def test_cancel_mocked(self, bridge, monkeypatch):
        """cancel() interrupts the SDK client."""
        mock_client = make_sdk_mock()
        _patch_sdk(monkeypatch, mock_client=mock_client)

        # Create session first
        await bridge.new_session(cwd=str(TEST_PROJECT))
        assert bridge._sdk_client is mock_client

        # Cancel
        await bridge.cancel(session_id=bridge._session_id)
        mock_client.interrupt.assert_called_once()
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
        assert spec.env.get("VS_ROOT_DIR") == str(TEST_PROJECT)
        assert "CLAUDECODE" not in spec.env

    @pytest.mark.asyncio
    async def test_run_subagent_with_mock_provider(self, tmp_path):
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
        assert spec.env.get("VS_SYSTEM_PROMPT")


# ---------------------------------------------------------------------------
# TestSetSessionModel
# ---------------------------------------------------------------------------


class TestSetSessionModel:
    """Test set_session_model updates the bridge model."""

    @pytest.mark.asyncio
    async def test_updates_model(self, bridge):
        """set_session_model updates bridge._model."""
        assert bridge._model == "claude-sonnet-4-5"
        await bridge.set_session_model(model_id="claude-opus-4-6", session_id="s1")
        assert bridge._model == "claude-opus-4-6"

    @pytest.mark.asyncio
    async def test_updates_sdk_options(self, bridge, monkeypatch):
        """set_session_model updates SDK client options.model in active session."""
        mock_client = make_sdk_mock()
        mock_client._options = FakeNamespace(model="claude-sonnet-4-5")
        _patch_sdk(monkeypatch, mock_client=mock_client)

        await bridge.new_session(cwd=str(TEST_PROJECT))
        await bridge.set_session_model(model_id="claude-opus-4-6", session_id="s1")

        assert bridge._model == "claude-opus-4-6"
        assert mock_client._options.model == "claude-opus-4-6"

    @pytest.mark.asyncio
    async def test_no_session_still_updates_model(self, bridge):
        """set_session_model works even without an active session."""
        assert bridge._sdk_client is None
        await bridge.set_session_model(model_id="claude-haiku-4-5", session_id="s1")
        assert bridge._model == "claude-haiku-4-5"

    @pytest.mark.asyncio
    async def test_no_options_attr_no_crash(self, bridge, monkeypatch):
        """set_session_model handles SDK client without _options attribute."""
        mock_client = make_sdk_mock()
        # Deliberately no _options attr (getattr returns None)
        if hasattr(mock_client, "_options"):
            del mock_client._options
        _patch_sdk(monkeypatch, mock_client=mock_client)

        await bridge.new_session(cwd=str(TEST_PROJECT))
        # Should not raise
        await bridge.set_session_model(model_id="claude-opus-4-6", session_id="s1")
        assert bridge._model == "claude-opus-4-6"

    @pytest.mark.asyncio
    async def test_returns_none(self, bridge):
        """set_session_model returns None (router normalizes to response)."""
        result = await bridge.set_session_model(
            model_id="claude-opus-4-6", session_id="s1"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_debug_logs(self, bridge_debug):
        """set_session_model logs in debug mode."""
        # Should not raise
        await bridge_debug.set_session_model(
            model_id="claude-opus-4-6", session_id="s1"
        )
        assert bridge_debug._model == "claude-opus-4-6"


# ---------------------------------------------------------------------------
# TestSetSessionMode
# ---------------------------------------------------------------------------


class TestSetSessionMode:
    """Test set_session_mode updates the bridge sandboxing mode."""

    @pytest.mark.asyncio
    async def test_updates_mode(self, bridge):
        """set_session_mode updates bridge._mode."""
        assert bridge._mode == "read-write"
        await bridge.set_session_mode(mode_id="read-only", session_id="s1")
        assert bridge._mode == "read-only"

    @pytest.mark.asyncio
    async def test_switch_to_read_write(self, monkeypatch):
        """set_session_mode can switch from read-only to read-write."""
        monkeypatch.setenv("VS_AGENT_MODE", "read-only")
        ro_bridge = ClaudeACPBridge()
        assert ro_bridge._mode == "read-only"

        await ro_bridge.set_session_mode(mode_id="read-write", session_id="s1")
        assert ro_bridge._mode == "read-write"

    @pytest.mark.asyncio
    async def test_updates_sandbox_callback_to_read_only(self, bridge, monkeypatch):
        """Switching to read-only mode installs a sandbox callback."""
        mock_client = make_sdk_mock()
        mock_client._options = FakeNamespace(can_use_tool=None)
        _patch_sdk(monkeypatch, mock_client=mock_client)

        await bridge.new_session(cwd=str(TEST_PROJECT))
        assert mock_client._options.can_use_tool is None

        await bridge.set_session_mode(mode_id="read-only", session_id="s1")
        assert bridge._mode == "read-only"
        assert mock_client._options.can_use_tool is not None

    @pytest.mark.asyncio
    async def test_updates_sandbox_callback_to_read_write(self, monkeypatch):
        """Switching to read-write mode removes the sandbox callback."""
        mock_client = make_sdk_mock()
        mock_client._options = FakeNamespace(can_use_tool=None)
        _patch_sdk(monkeypatch, mock_client=mock_client)

        monkeypatch.setenv("VS_AGENT_MODE", "read-only")
        ro_bridge = ClaudeACPBridge()
        from .conftest import FakeConn

        ro_bridge.on_connect(FakeConn())

        await ro_bridge.new_session(cwd=str(TEST_PROJECT))
        # set_session_mode to read-only installs the callback
        await ro_bridge.set_session_mode(mode_id="read-only", session_id="s1")
        assert mock_client._options.can_use_tool is not None

        await ro_bridge.set_session_mode(mode_id="read-write", session_id="s1")
        assert ro_bridge._mode == "read-write"
        assert mock_client._options.can_use_tool is None

    @pytest.mark.asyncio
    async def test_no_session_still_updates_mode(self, bridge):
        """set_session_mode works even without an active session."""
        assert bridge._sdk_client is None
        await bridge.set_session_mode(mode_id="read-only", session_id="s1")
        assert bridge._mode == "read-only"

    @pytest.mark.asyncio
    async def test_no_options_attr_no_crash(self, bridge, monkeypatch):
        """set_session_mode handles SDK client without _options attribute."""
        mock_client = make_sdk_mock()
        if hasattr(mock_client, "_options"):
            del mock_client._options
        _patch_sdk(monkeypatch, mock_client=mock_client)

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


# ---------------------------------------------------------------------------
# TestAuthenticate
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# TestListSessions
# ---------------------------------------------------------------------------


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
    async def test_returns_session_info_after_new_session(self, bridge, monkeypatch):
        """list_sessions returns SessionInfo after new_session creates one."""
        from acp.schema import ListSessionsResponse, SessionInfo

        _patch_sdk(monkeypatch)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        result = await bridge.list_sessions()
        assert isinstance(result, ListSessionsResponse)
        assert len(result.sessions) == 1

        info = result.sessions[0]
        assert isinstance(info, SessionInfo)
        assert info.session_id == session_id
        assert info.cwd == str(TEST_PROJECT)
        assert info.title == "claude-sonnet-4-5 (read-write)"
        assert info.updated_at is not None

    @pytest.mark.asyncio
    async def test_cwd_filter(self, bridge, monkeypatch):
        """list_sessions filters sessions by cwd when specified."""
        _patch_sdk(monkeypatch)

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
    async def test_multiple_sessions(self, bridge, monkeypatch):
        """list_sessions returns all tracked sessions."""
        _patch_sdk(monkeypatch)

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
    async def test_cwd_filter_no_match(self, bridge, monkeypatch):
        """list_sessions with non-matching cwd returns empty list."""
        _patch_sdk(monkeypatch)
        await bridge.new_session(cwd=str(TEST_PROJECT))

        result = await bridge.list_sessions(cwd=str(TEST_PROJECT / "nonexistent"))
        assert result.sessions == []


# ---------------------------------------------------------------------------
# TestLoadSession
# ---------------------------------------------------------------------------


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
    async def test_loads_existing_session(self, bridge, monkeypatch):
        """load_session returns LoadSessionResponse for a known session."""
        from acp.schema import LoadSessionResponse

        factory = _patch_sdk(monkeypatch)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        # Swap to a fresh mock for the load reconnection
        factory.client = make_sdk_mock()

        result = await bridge.load_session(cwd=str(TEST_PROJECT), session_id=session_id)
        assert result is not None
        assert isinstance(result, LoadSessionResponse)

    @pytest.mark.asyncio
    async def test_disconnects_previous_client(self, bridge, monkeypatch):
        """load_session disconnects the previous SDK client before reconnecting."""
        original_mock = make_sdk_mock()
        factory = _patch_sdk(monkeypatch, mock_client=original_mock)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        # Reset disconnect tracking, then load
        original_mock.disconnect.reset_mock()
        new_mock = make_sdk_mock()
        factory.client = new_mock

        await bridge.load_session(cwd=str(TEST_PROJECT), session_id=session_id)

        original_mock.disconnect.assert_called_once()
        new_mock.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_config_preserved_from_stored_state(self, bridge, monkeypatch):
        """load_session rebuilds SDK client with model/mode from stored state."""
        factory = _patch_sdk(monkeypatch)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        # Mutate bridge-level model to prove load restores from stored state
        bridge._model = "claude-opus-4-6"

        factory.client = make_sdk_mock()

        new_cwd = str(TEST_PROJECT / "new-cwd")
        await bridge.load_session(cwd=new_cwd, session_id=session_id)

        # Bridge model should be restored from stored state, not the mutated value
        assert bridge._model == "claude-sonnet-4-5"
        assert bridge._session_id == session_id
        assert bridge._root_dir == new_cwd

    @pytest.mark.asyncio
    async def test_marks_session_connected(self, bridge, monkeypatch):
        """load_session sets the session state back to connected=True."""
        factory = _patch_sdk(monkeypatch)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        # Mark disconnected (as cancel would do)
        bridge._sessions[session_id].connected = False

        factory.client = make_sdk_mock()

        await bridge.load_session(cwd=str(TEST_PROJECT), session_id=session_id)
        assert bridge._sessions[session_id].connected is True


# ---------------------------------------------------------------------------
# TestResumeSession
# ---------------------------------------------------------------------------


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
    async def test_resumes_existing_session(self, bridge, monkeypatch):
        """resume_session returns ResumeSessionResponse for a known session."""
        from acp.schema import ResumeSessionResponse

        factory = _patch_sdk(monkeypatch)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        factory.client = make_sdk_mock()

        result = await bridge.resume_session(
            cwd=str(TEST_PROJECT), session_id=session_id
        )
        assert result is not None
        assert isinstance(result, ResumeSessionResponse)

    @pytest.mark.asyncio
    async def test_disconnects_previous_client(self, bridge, monkeypatch):
        """resume_session disconnects the previous SDK client."""
        original_mock = make_sdk_mock()
        factory = _patch_sdk(monkeypatch, mock_client=original_mock)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        original_mock.disconnect.reset_mock()
        new_mock = make_sdk_mock()
        factory.client = new_mock

        await bridge.resume_session(cwd=str(TEST_PROJECT), session_id=session_id)

        original_mock.disconnect.assert_called_once()
        new_mock.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_config_preserved_from_stored_state(self, bridge, monkeypatch):
        """resume_session rebuilds SDK client with config from stored state."""
        factory = _patch_sdk(monkeypatch)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        # Mutate bridge-level model
        bridge._model = "claude-opus-4-6"

        factory.client = make_sdk_mock()

        new_cwd = str(TEST_PROJECT / "new-cwd")
        await bridge.resume_session(cwd=new_cwd, session_id=session_id)

        # Bridge model restored from stored state
        assert bridge._model == "claude-sonnet-4-5"
        assert bridge._session_id == session_id
        assert bridge._root_dir == new_cwd

    @pytest.mark.asyncio
    async def test_marks_session_connected(self, bridge, monkeypatch):
        """resume_session sets the session state back to connected=True."""
        factory = _patch_sdk(monkeypatch)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        bridge._sessions[session_id].connected = False

        factory.client = make_sdk_mock()

        await bridge.resume_session(cwd=str(TEST_PROJECT), session_id=session_id)
        assert bridge._sessions[session_id].connected is True


# ---------------------------------------------------------------------------
# TestForkSession
# ---------------------------------------------------------------------------


class TestForkSession:
    """Test fork_session creates a new session from an existing one."""

    @pytest.mark.asyncio
    async def test_raises_for_unknown_session(self, bridge):
        """fork_session raises RuntimeError for a session_id not in _sessions."""
        with pytest.raises(RuntimeError, match=r"Cannot fork.*not found"):
            await bridge.fork_session(cwd=str(TEST_PROJECT), session_id="nonexistent")

    @pytest.mark.asyncio
    async def test_returns_fork_response_with_new_id(self, bridge, monkeypatch):
        """fork_session returns ForkSessionResponse with a new session_id."""
        from acp.schema import ForkSessionResponse

        factory = _patch_sdk(monkeypatch)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        source_id = bridge._session_id

        new_mock = make_sdk_mock()
        factory.client = new_mock

        result = await bridge.fork_session(cwd=str(TEST_PROJECT), session_id=source_id)
        assert isinstance(result, ForkSessionResponse)
        # The new session_id must differ from the source
        assert result.session_id != source_id
        assert result.session_id is not None

    @pytest.mark.asyncio
    async def test_clones_config_from_source(self, bridge, monkeypatch):
        """fork_session clones model and mode from the source session."""
        factory = _patch_sdk(monkeypatch)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        source_id = bridge._session_id

        factory.client = make_sdk_mock()

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
    async def test_new_session_tracked(self, bridge, monkeypatch):
        """fork_session stores the new session in self._sessions."""
        factory = _patch_sdk(monkeypatch)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        source_id = bridge._session_id

        factory.client = make_sdk_mock()

        result = await bridge.fork_session(cwd=str(TEST_PROJECT), session_id=source_id)
        new_id = result.session_id

        assert new_id in bridge._sessions
        assert bridge._sessions[new_id].session_id == new_id
        assert bridge._sessions[new_id].connected is True
        # Source session should still exist
        assert source_id in bridge._sessions

    @pytest.mark.asyncio
    async def test_disconnects_previous_client(self, bridge, monkeypatch):
        """fork_session disconnects the current SDK client before forking."""
        original_mock = make_sdk_mock()
        factory = _patch_sdk(monkeypatch, mock_client=original_mock)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        source_id = bridge._session_id

        original_mock.disconnect.reset_mock()
        new_mock = make_sdk_mock()
        factory.client = new_mock

        await bridge.fork_session(cwd=str(TEST_PROJECT), session_id=source_id)

        original_mock.disconnect.assert_called_once()
        new_mock.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_bridge_state_updated_to_forked_session(self, bridge, monkeypatch):
        """fork_session updates bridge._session_id to the new forked session."""
        factory = _patch_sdk(monkeypatch)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        source_id = bridge._session_id

        new_mock = make_sdk_mock()
        factory.client = new_mock

        result = await bridge.fork_session(cwd=str(TEST_PROJECT), session_id=source_id)
        assert bridge._session_id == result.session_id
        assert bridge._sdk_client is new_mock


# ---------------------------------------------------------------------------
# TestSessionTracking
# ---------------------------------------------------------------------------


class TestSessionTracking:
    """Test that new_session stores _SessionState and cancel marks disconnected."""

    @pytest.mark.asyncio
    async def test_new_session_stores_session_state(self, bridge, monkeypatch):
        """new_session stores a _SessionState in self._sessions."""
        from protocol.acp.claude_bridge import _SessionState

        _patch_sdk(monkeypatch)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        assert session_id in bridge._sessions
        state = bridge._sessions[session_id]
        assert isinstance(state, _SessionState)
        assert state.session_id == session_id
        assert state.cwd == str(TEST_PROJECT)
        assert state.model == "claude-sonnet-4-5"
        assert state.mode == "read-write"
        assert state.mcp_servers == []
        assert state.connected is True
        assert state.created_at is not None

    @pytest.mark.asyncio
    async def test_cancel_marks_session_disconnected(self, bridge, monkeypatch):
        """cancel sets the session's connected flag to False."""
        _patch_sdk(monkeypatch)
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        assert bridge._sessions[session_id].connected is True
        await bridge.cancel(session_id=session_id)
        assert bridge._sessions[session_id].connected is False

    @pytest.mark.asyncio
    async def test_multiple_sessions_tracked_independently(self, bridge, monkeypatch):
        """Each new_session creates a separate _SessionState entry."""
        _patch_sdk(monkeypatch)

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


# ---------------------------------------------------------------------------
# TestBridgeFeatureConfig — Phase 5: env var config passthrough
# ---------------------------------------------------------------------------


class TestBridgeFeatureConfig:
    """Verify bridge reads VS_* env vars and wires them to ClaudeAgentOptions."""

    def test_max_turns_from_env(self, monkeypatch):
        monkeypatch.setenv("VS_MAX_TURNS", "10")
        bridge = ClaudeACPBridge()
        assert bridge._max_turns == 10

    def test_budget_from_env(self, monkeypatch):
        monkeypatch.setenv("VS_BUDGET_USD", "2.5")
        bridge = ClaudeACPBridge()
        assert bridge._budget_usd == 2.5

    def test_allowed_tools_from_env(self, monkeypatch):
        monkeypatch.setenv("VS_ALLOWED_TOOLS", "Glob, Read, Grep")
        bridge = ClaudeACPBridge()
        assert bridge._allowed_tools == ["Glob", "Read", "Grep"]

    def test_disallowed_tools_from_env(self, monkeypatch):
        monkeypatch.setenv("VS_DISALLOWED_TOOLS", "Bash, Write")
        bridge = ClaudeACPBridge()
        assert bridge._disallowed_tools == ["Bash", "Write"]

    def test_effort_from_env(self, monkeypatch):
        monkeypatch.setenv("VS_EFFORT", "high")
        bridge = ClaudeACPBridge()
        assert bridge._effort == "high"

    def test_fallback_model_from_env(self, monkeypatch):
        monkeypatch.setenv("VS_FALLBACK_MODEL", "claude-haiku-4-5")
        bridge = ClaudeACPBridge()
        assert bridge._fallback_model == "claude-haiku-4-5"

    def test_include_dirs_from_env(self, monkeypatch):
        monkeypatch.setenv("VS_INCLUDE_DIRS", ".vault, src")
        bridge = ClaudeACPBridge()
        assert bridge._include_dirs == [".vault", "src"]

    def test_output_format_from_env(self, monkeypatch):
        monkeypatch.setenv("VS_OUTPUT_FORMAT", "json")
        bridge = ClaudeACPBridge()
        assert bridge._output_format == "json"

    def test_defaults_when_no_env(self):
        """Without VS_* env vars, all feature fields default to None/empty."""
        bridge = ClaudeACPBridge()
        assert bridge._max_turns is None
        assert bridge._budget_usd is None
        assert bridge._allowed_tools == []
        assert bridge._disallowed_tools == []
        assert bridge._effort is None
        assert bridge._fallback_model is None
        assert bridge._include_dirs == []
        assert bridge._output_format is None

    def test_build_options_includes_features(self, monkeypatch):
        """_build_options() passes features to ClaudeAgentOptions kwargs."""
        monkeypatch.setenv("VS_MAX_TURNS", "15")
        monkeypatch.setenv("VS_BUDGET_USD", "3.0")
        monkeypatch.setenv("VS_EFFORT", "max")
        monkeypatch.setenv("VS_FALLBACK_MODEL", "claude-haiku-4-5")
        monkeypatch.setenv("VS_ALLOWED_TOOLS", "Glob, Read")
        monkeypatch.setenv("VS_DISALLOWED_TOOLS", "Bash")
        monkeypatch.setenv("VS_INCLUDE_DIRS", ".vault")
        bridge = ClaudeACPBridge()

        # Capture kwargs by replacing ClaudeAgentOptions with a recorder
        captured = {}

        class OptionsRecorder:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(
            "protocol.acp.claude_bridge.ClaudeAgentOptions", OptionsRecorder
        )
        bridge._build_options(str(TEST_PROJECT), {}, None)

        assert captured["max_turns"] == 15
        assert captured["max_budget_usd"] == 3.0
        assert captured["effort"] == "max"
        assert captured["fallback_model"] == "claude-haiku-4-5"
        assert captured["allowed_tools"] == ["Glob", "Read"]
        assert captured["disallowed_tools"] == ["Bash"]
        assert captured["add_dirs"] == [".vault"]

    def test_build_options_omits_none_features(self, monkeypatch):
        """_build_options() omits features that are None/empty."""
        bridge = ClaudeACPBridge()

        captured = {}

        class OptionsRecorder:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(
            "protocol.acp.claude_bridge.ClaudeAgentOptions", OptionsRecorder
        )
        bridge._build_options(str(TEST_PROJECT), {}, None)

        assert "max_turns" not in captured
        assert "max_budget_usd" not in captured
        assert "effort" not in captured
        assert "fallback_model" not in captured
        assert "allowed_tools" not in captured
        assert "disallowed_tools" not in captured
        assert "add_dirs" not in captured
        assert "output_format" not in captured

    def test_output_format_json_passed_to_sdk(self, monkeypatch):
        """_build_options() passes output_format dict when json."""
        monkeypatch.setenv("VS_OUTPUT_FORMAT", "json")
        bridge = ClaudeACPBridge()

        captured = {}

        class OptionsRecorder:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(
            "protocol.acp.claude_bridge.ClaudeAgentOptions",
            OptionsRecorder,
        )
        bridge._build_options(str(TEST_PROJECT), {}, None)

        assert captured["output_format"] == {
            "type": "json_object",
        }

    def test_output_format_text_not_passed(self, monkeypatch):
        """_build_options() omits output_format for text."""
        monkeypatch.setenv("VS_OUTPUT_FORMAT", "text")
        bridge = ClaudeACPBridge()

        captured = {}

        class OptionsRecorder:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(
            "protocol.acp.claude_bridge.ClaudeAgentOptions",
            OptionsRecorder,
        )
        bridge._build_options(str(TEST_PROJECT), {}, None)

        assert "output_format" not in captured
