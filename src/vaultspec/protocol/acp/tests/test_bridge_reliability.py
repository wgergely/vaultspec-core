"""Reliability tests for ClaudeACPBridge.

Covers:
- Dynamic permission mode switching.
- Session recovery (load unknown ID).
- Tool use error event handling.
"""

from __future__ import annotations

import pytest
from acp.schema import TextContentBlock, ToolCallProgress
from claude_agent_sdk import ResultMessage
from claude_agent_sdk._errors import MessageParseError
from claude_agent_sdk.types import StreamEvent

from tests.constants import TEST_PROJECT

from .conftest import make_di_bridge, make_test_client, make_test_conn

pytestmark = [pytest.mark.unit]


class TestPermissionModes:
    """Test dynamic permission mode switching."""

    @pytest.mark.asyncio
    async def test_prompt_switches_permission_mode(self):
        """Prompt with magic string recreates client with new mode."""
        bridge, _holder, captured_options = make_di_bridge()
        conn = make_test_conn()
        bridge.on_connect(conn)

        resp = await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = resp.session_id

        # Initial mode should be bypassPermissions
        assert bridge._sessions[session_id].permission_mode == "bypassPermissions"
        assert captured_options.get("permission_mode") == "bypassPermissions"

        # Send prompt with magic string
        prompt = [
            TextContentBlock(type="text", text="[ACP:PERMISSION:ACCEPT_EDITS] please")
        ]

        # We need to simulate the client recreation. make_di_bridge uses a holder.
        # The new client will be the *same* instance (holder.client) but options_factory
        # will be called again.

        await bridge.prompt(prompt=prompt, session_id=session_id)

        # Check state update
        assert bridge._sessions[session_id].permission_mode == "acceptEdits"

        # Check options update (captured from the *second* client creation)
        assert captured_options.get("permission_mode") == "acceptEdits"


class TestSessionRecovery:
    """Test session recovery mechanisms."""

    @pytest.mark.asyncio
    async def test_load_session_recovers_unknown_id(self):
        """load_session creates a new session if ID not found."""
        bridge, _holder, _captured = make_di_bridge()
        conn = make_test_conn()
        bridge.on_connect(conn)

        # Load unknown session ID
        unknown_id = "recovered-session-123"
        await bridge.load_session(cwd=str(TEST_PROJECT), session_id=unknown_id)

        # Verify session created
        assert unknown_id in bridge._sessions
        state = bridge._sessions[unknown_id]
        assert state.connected is True
        assert state.sdk_client is not None


class TestToolErrors:
    """Test tool error event handling."""

    @pytest.mark.asyncio
    async def test_tool_use_error_event_emits_failed(self):
        """tool_use_error event emits ToolCallProgress with status='failed'."""
        bridge, _holder, _captured = make_di_bridge()
        conn = make_test_conn()
        bridge.on_connect(conn)

        resp = await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = resp.session_id

        # Pre-populate pending tool to verify title lookup
        bridge._pending_tools["toolu_err"] = "Bash"

        event = StreamEvent(
            uuid="evt-err",
            session_id=session_id,
            event={
                "type": "tool_use_error",
                "tool_use_id": "toolu_err",
                "error": "Command failed",
            },
        )

        await bridge._emit_stream_event(event, session_id)

        assert len(conn.session_update_calls) == 1
        update = conn.session_update_calls[0]["update"]
        assert isinstance(update, ToolCallProgress)
        assert update.tool_call_id == "toolu_err"
        assert update.status == "failed"
        assert update.title == "Bash"
        assert update.raw_output == {"error": "Command failed"}
        # Access pydantic model attributes
        assert update.content[0].content.text == "Error: Command failed"


class TestStreamRetries:
    """Test that the bridge retries the stream on MessageParseError."""

    @pytest.mark.asyncio
    async def test_skips_parse_error_continues_to_result(self):
        """prompt() handles MessageParseError and continues until ResultMessage."""
        from acp.schema import TextContentBlock

        result_msg = ResultMessage(
            subtype="result",
            duration_ms=0,
            duration_api_ms=0,
            is_error=False,
            num_turns=1,
            session_id="s1",
            result="Success",
        )

        # Create a client that raises MessageParseError ONCE
        test_client = make_test_client(messages=[result_msg])

        # We override receive_response to simulate a fail-then-success sequence
        original_receive = test_client.receive_response
        call_count = 0

        def failing_receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                from .conftest import AsyncItemIterator

                return AsyncItemIterator([], raise_exc=MessageParseError("rate_limit"))
            return original_receive()

        test_client.receive_response = failing_receive

        bridge, _holder, _captured = make_di_bridge(client=test_client)
        bridge.on_connect(make_test_conn())
        await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = bridge._session_id

        prompt_blocks = [TextContentBlock(type="text", text="test")]

        result = await bridge.prompt(prompt=prompt_blocks, session_id=session_id)

        assert result.stop_reason == "end_turn"
        assert call_count == 2
        assert test_client.disconnect_count == 0
