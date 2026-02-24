"""Resilience tests for ClaudeACPBridge.

Covers: cancel, cancel tracking, granular error handling (warning logs).
"""

from __future__ import annotations

import logging
from typing import cast

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ContentBlock,
    TextBlock,
    UserMessage,
)

from tests.constants import TEST_PROJECT

from ..claude_bridge import ClaudeACPBridge
from .conftest import (
    make_di_bridge,
    make_test_client,
    make_test_conn,
)

pytestmark = [pytest.mark.unit]


class _UnknownBlock:
    """Sentinel for testing unsupported content block types."""


class TestCancel:
    """Test session cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_interrupts_sdk(self):
        """cancel() calls interrupt() on the SDK client."""
        test_client = make_test_client()
        bridge, _holder, _captured = make_di_bridge(client=test_client)

        resp = await bridge.new_session(cwd=str(TEST_PROJECT))
        await bridge.cancel(session_id=resp.session_id)

        assert test_client.interrupt_count == 1

    @pytest.mark.asyncio
    async def test_cancel_no_session(self, bridge):
        """cancel() with no active session does not raise."""
        await bridge.cancel(session_id="nonexistent")

    @pytest.mark.asyncio
    async def test_cancel_returns_none(self):
        """cancel() returns None."""
        bridge, _holder, _captured = make_di_bridge()

        resp = await bridge.new_session(cwd=str(TEST_PROJECT))
        result = await bridge.cancel(session_id=resp.session_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_handles_interrupt_error(self):
        """cancel() catches exceptions from interrupt()."""
        test_client = make_test_client()
        test_client._interrupt_hook = RuntimeError("interrupt failed")
        bridge, _holder, _captured = make_di_bridge(client=test_client)

        resp = await bridge.new_session(cwd=str(TEST_PROJECT))
        # Should not raise
        await bridge.cancel(session_id=resp.session_id)


class TestCancelTracking:
    """Test cancel tracking: _cancelled flag, 'cancelled' stop reason."""

    @pytest.mark.asyncio
    async def test_cancel_sets_flag(self, bridge):
        """cancel() sets _cancelled to True even without an SDK client."""
        # This tests global flag behavior which is kept for compat
        assert bridge._cancelled is False
        await bridge.cancel(session_id="s1")
        assert bridge._cancelled is True

    @pytest.mark.asyncio
    async def test_cancel_sets_flag_with_session(self):
        """cancel() sets _cancelled to True when an SDK client exists."""
        bridge, _holder, _captured = make_di_bridge()

        resp = await bridge.new_session(cwd=str(TEST_PROJECT))

        await bridge.cancel(session_id=resp.session_id)
        # Check per-session event
        state = bridge._sessions[resp.session_id]
        assert state.cancel_event.is_set()

    @pytest.mark.asyncio
    async def test_cancel_flag_set_before_interrupt(self):
        """cancel() sets _cancelled before calling interrupt()."""
        test_client = make_test_client()
        bridge, _holder, _captured = make_di_bridge(client=test_client)

        observed_cancelled = []

        def capture_flag():
            # Check global flag as we don't have session_id here easily
            observed_cancelled.append(bridge._cancelled)

        test_client._interrupt_hook = capture_flag

        resp = await bridge.new_session(cwd=str(TEST_PROJECT))
        await bridge.cancel(session_id=resp.session_id)

        assert observed_cancelled == [True]

    @pytest.mark.asyncio
    async def test_prompt_resets_cancelled_flag(self):
        """prompt() resets cancel_event to False at the start."""
        from acp.schema import TextContentBlock

        bridge, _holder, _captured = make_di_bridge()
        conn = make_test_conn()
        bridge.on_connect(conn)

        resp = await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = resp.session_id

        # Simulate a prior cancel
        bridge._sessions[session_id].cancel_event.set()

        prompt_blocks = [TextContentBlock(type="text", text="hello again")]
        result = await bridge.prompt(prompt=prompt_blocks, session_id=session_id)

        # Flag should be reset
        assert bridge._sessions[session_id].cancel_event.is_set() is False
        assert result.stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_cancelled_during_streaming_returns_cancelled(self):
        """When cancel_event is set during streaming, stop_reason is 'cancelled'."""
        from acp.schema import TextContentBlock

        text_block = TextBlock(text="partial response")
        msg = AssistantMessage(content=[text_block], model="test-model")

        test_client = make_test_client(messages=[msg])
        bridge, _holder, _captured = make_di_bridge(client=test_client)
        conn = make_test_conn()
        bridge.on_connect(conn)

        resp = await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = resp.session_id

        # Set cancel_event DURING query()
        def _set_cancelled(*_args, **_kwargs):
            bridge._sessions[session_id].cancel_event.set()

        test_client._query_hook = _set_cancelled

        prompt_blocks = [TextContentBlock(type="text", text="test")]
        result = await bridge.prompt(prompt=prompt_blocks, session_id=session_id)
        assert result.stop_reason == "cancelled"

    @pytest.mark.asyncio
    async def test_cancelled_skips_emit_for_remaining_messages(self):
        """When cancelled, remaining messages are NOT emitted."""
        from acp.schema import TextContentBlock

        text_block = TextBlock(text="should not be emitted")

        msg1 = AssistantMessage(content=[text_block], model="test-model")
        msg2 = AssistantMessage(content=[text_block], model="test-model")

        test_client = make_test_client(messages=[msg1, msg2])
        bridge, _holder, _captured = make_di_bridge(client=test_client)
        conn = make_test_conn()
        bridge.on_connect(conn)

        resp = await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = resp.session_id

        # Set cancel_event DURING query()
        def _set_cancelled(*_args, **_kwargs):
            bridge._sessions[session_id].cancel_event.set()

        test_client._query_hook = _set_cancelled

        prompt_blocks = [TextContentBlock(type="text", text="test")]
        await bridge.prompt(prompt=prompt_blocks, session_id=session_id)

        assert len(conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_cancel_then_new_prompt_works_normally(self):
        """After cancel, a subsequent prompt() resets and works normally."""
        from acp.schema import TextContentBlock

        test_client = make_test_client()
        bridge, _holder, _captured = make_di_bridge(client=test_client)
        conn = make_test_conn()
        bridge.on_connect(conn)

        resp = await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = resp.session_id

        # Cancel first
        await bridge.cancel(session_id=session_id)
        assert bridge._sessions[session_id].cancel_event.is_set()

        # Verify no disconnect occurred
        assert test_client.disconnect_count == 0
        state = bridge._sessions[session_id]
        assert state.connected is True

        # New prompt resets the flag and completes normally
        prompt_blocks = [TextContentBlock(type="text", text="continue")]
        result = await bridge.prompt(prompt=prompt_blocks, session_id=session_id)
        assert bridge._sessions[session_id].cancel_event.is_set() is False
        assert result.stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_cancel_does_not_disconnect(self):
        """cancel() interrupts stream but keeps session connected."""
        test_client = make_test_client()
        bridge, _holder, _captured = make_di_bridge(client=test_client)

        resp = await bridge.new_session(cwd=str(TEST_PROJECT))
        session_id = resp.session_id

        await bridge.cancel(session_id=session_id)

        assert test_client.interrupt_count == 1
        assert test_client.disconnect_count == 0
        assert bridge._sessions[session_id].connected is True


class TestGranularErrorHandling:
    """Test granular error handling: warning logs for edge cases."""

    @pytest.mark.asyncio
    async def test_untracked_tool_id_logs_warning(
        self,
        connected_bridge,
        test_conn,
        caplog,
    ):
        """UserMessage with tool_use_id not in _pending_tools triggers warning."""
        msg = UserMessage(parent_tool_use_id="toolu_orphan", content=[])

        with caplog.at_level(
            logging.WARNING, logger="vaultspec.protocol.acp.claude_bridge"
        ):
            await connected_bridge._emit_user_message(msg, "s1")

        assert any("untracked" in record.message.lower() for record in caplog.records)
        assert any("toolu_orphan" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_untracked_tool_id_still_emits_update(
        self, connected_bridge, test_conn
    ):
        """Even with an untracked tool_use_id, a ToolCallProgress is still emitted."""
        from acp.schema import ToolCallProgress

        msg = UserMessage(parent_tool_use_id="toolu_untracked", content=[])

        await connected_bridge._emit_user_message(msg, "s1")

        assert len(test_conn.session_update_calls) == 1
        call_kwargs = test_conn.session_update_calls[-1]
        update = call_kwargs["update"]
        assert isinstance(update, ToolCallProgress)
        assert update.tool_call_id == "toolu_untracked"
        assert update.title is None

    @pytest.mark.asyncio
    async def test_tracked_tool_id_no_warning(
        self,
        connected_bridge,
        test_conn,
        caplog,
    ):
        """UserMessage with a tracked tool_use_id does NOT trigger warning."""
        connected_bridge._pending_tools["toolu_tracked"] = "Read"

        msg = UserMessage(parent_tool_use_id="toolu_tracked", content=[])

        with caplog.at_level(
            logging.WARNING, logger="vaultspec.protocol.acp.claude_bridge"
        ):
            await connected_bridge._emit_user_message(msg, "s1")

        assert not any(
            "untracked" in record.message.lower() for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_unknown_block_type_logs_warning(
        self,
        connected_bridge,
        test_conn,
        caplog,
    ):
        """Unsupported content block type in AssistantMessage triggers warning."""
        unknown_block = _UnknownBlock()

        msg = AssistantMessage(
            content=cast("list[ContentBlock]", [unknown_block]),
            model="test-model",
        )

        with caplog.at_level(
            logging.WARNING, logger="vaultspec.protocol.acp.claude_bridge"
        ):
            await connected_bridge._emit_assistant(msg, "s1")

        assert any("unsupported" in record.message.lower() for record in caplog.records)

    @pytest.mark.asyncio
    async def test_unknown_block_type_not_emitted(self, connected_bridge, test_conn):
        """Unsupported content block type does not emit a session_update."""
        unknown_block = _UnknownBlock()

        msg = AssistantMessage(
            content=cast("list[ContentBlock]", [unknown_block]),
            model="test-model",
        )

        await connected_bridge._emit_assistant(msg, "s1")

        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_unknown_block_type_debug_extra_detail(self, test_conn, caplog):
        """In debug mode, unknown block type also logs block details at DEBUG."""
        bridge_dbg = ClaudeACPBridge(model="test", debug=True)
        bridge_dbg.on_connect(test_conn)

        unknown_block = _UnknownBlock()

        msg = AssistantMessage(
            content=cast("list[ContentBlock]", [unknown_block]),
            model="test-model",
        )

        with caplog.at_level(
            logging.DEBUG, logger="vaultspec.protocol.acp.claude_bridge"
        ):
            await bridge_dbg._emit_assistant(msg, "s1")

        # Should have both WARNING (unsupported) and DEBUG (details)
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(warning_records) >= 1
        assert len(debug_records) >= 1
        assert any(
            "detail" in r.message.lower() or "block" in r.message.lower()
            for r in debug_records
        )

    @pytest.mark.asyncio
    async def test_unknown_block_type_no_debug_no_detail(
        self,
        connected_bridge,
        test_conn,
        caplog,
    ):
        """In non-debug mode, unknown block type logs warning but not debug detail."""
        unknown_block = _UnknownBlock()

        msg = AssistantMessage(
            content=cast("list[ContentBlock]", [unknown_block]),
            model="test-model",
        )

        with caplog.at_level(
            logging.DEBUG, logger="vaultspec.protocol.acp.claude_bridge"
        ):
            await connected_bridge._emit_assistant(msg, "s1")

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(warning_records) >= 1
        # Non-debug bridge should NOT emit the extra DEBUG-level detail log
        assert len(debug_records) == 0

    @pytest.mark.asyncio
    async def test_warning_includes_block_type_name(
        self,
        connected_bridge,
        test_conn,
        caplog,
    ):
        """Warning log for unsupported block includes the block's class name."""
        unknown_block = _UnknownBlock()

        msg = AssistantMessage(
            content=cast("list[ContentBlock]", [unknown_block]),
            model="test-model",
        )

        with caplog.at_level(
            logging.WARNING, logger="vaultspec.protocol.acp.claude_bridge"
        ):
            await connected_bridge._emit_assistant(msg, "s1")

        # The warning should contain the class name of the unknown block
        assert any("_UnknownBlock" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_mixed_known_and_unknown_blocks(
        self, connected_bridge, test_conn, caplog
    ):
        """Known blocks are emitted normally; unknown blocks trigger warning only."""
        text_block = TextBlock(text="valid text")

        unknown_block = _UnknownBlock()

        msg = AssistantMessage(
            content=cast("list[ContentBlock]", [text_block, unknown_block]),
            model="test-model",
        )

        with caplog.at_level(
            logging.WARNING, logger="vaultspec.protocol.acp.claude_bridge"
        ):
            await connected_bridge._emit_assistant(msg, "s1")

        # TextBlock is skipped in _emit_assistant, so 0 calls
        assert len(test_conn.session_update_calls) == 0
        assert any("unsupported" in record.message.lower() for record in caplog.records)
