"""Resilience tests for ClaudeACPBridge.

Covers: cancel, cancel tracking, granular error handling (warning logs).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from protocol.acp.claude_bridge import ClaudeACPBridge

from .conftest import make_sdk_mock

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# TestCancel
# ---------------------------------------------------------------------------


class TestCancel:
    """Test session cancellation."""

    @pytest.mark.asyncio
    @patch("protocol.acp.claude_bridge.ClaudeSDKClient")
    @patch("protocol.acp.claude_bridge.ClaudeAgentOptions")
    async def test_cancel_interrupts_sdk(self, _mock_options_cls, mock_sdk_cls, bridge):
        """cancel() calls interrupt() on the SDK client."""
        mock_instance = make_sdk_mock()
        mock_sdk_cls.return_value = mock_instance

        await bridge.new_session(cwd="/workspace")
        await bridge.cancel(session_id="s1")

        mock_instance.interrupt.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_no_session(self, bridge):
        """cancel() with no active session does not raise."""
        await bridge.cancel(session_id="nonexistent")

    @pytest.mark.asyncio
    @patch("protocol.acp.claude_bridge.ClaudeSDKClient")
    @patch("protocol.acp.claude_bridge.ClaudeAgentOptions")
    async def test_cancel_returns_none(self, _mock_options_cls, mock_sdk_cls, bridge):
        """cancel() returns None."""
        mock_sdk_cls.return_value = make_sdk_mock()

        await bridge.new_session(cwd="/workspace")
        result = await bridge.cancel(session_id="s1")
        assert result is None

    @pytest.mark.asyncio
    @patch("protocol.acp.claude_bridge.ClaudeSDKClient")
    @patch("protocol.acp.claude_bridge.ClaudeAgentOptions")
    async def test_cancel_handles_interrupt_error(
        self, _mock_options_cls, mock_sdk_cls, bridge
    ):
        """cancel() catches exceptions from interrupt()."""
        mock_instance = make_sdk_mock()
        mock_instance.interrupt.side_effect = RuntimeError("interrupt failed")
        mock_sdk_cls.return_value = mock_instance

        await bridge.new_session(cwd="/workspace")
        # Should not raise
        await bridge.cancel(session_id="s1")


# ---------------------------------------------------------------------------
# TestCancelTracking
# ---------------------------------------------------------------------------


class TestCancelTracking:
    """Test cancel tracking: _cancelled flag, 'cancelled' stop reason."""

    @pytest.mark.asyncio
    async def test_cancel_sets_flag(self, bridge):
        """cancel() sets _cancelled to True even without an SDK client."""
        assert bridge._cancelled is False
        await bridge.cancel(session_id="s1")
        assert bridge._cancelled is True

    @pytest.mark.asyncio
    @patch("protocol.acp.claude_bridge.ClaudeSDKClient")
    @patch("protocol.acp.claude_bridge.ClaudeAgentOptions")
    async def test_cancel_sets_flag_with_session(
        self, _mock_options_cls, mock_sdk_cls, bridge
    ):
        """cancel() sets _cancelled to True when an SDK client exists."""
        mock_sdk_cls.return_value = make_sdk_mock()
        await bridge.new_session(cwd="/workspace")

        await bridge.cancel(session_id="s1")
        assert bridge._cancelled is True

    @pytest.mark.asyncio
    @patch("protocol.acp.claude_bridge.ClaudeSDKClient")
    @patch("protocol.acp.claude_bridge.ClaudeAgentOptions")
    async def test_cancel_flag_set_before_interrupt(
        self, _mock_options_cls, mock_sdk_cls, bridge
    ):
        """cancel() sets _cancelled before calling interrupt().

        Verifies the flag is already True when interrupt() is invoked so that
        the streaming loop can observe the cancellation immediately.
        """
        observed_cancelled = []
        mock_instance = make_sdk_mock()

        def capture_flag():
            observed_cancelled.append(bridge._cancelled)

        mock_instance.interrupt = MagicMock(side_effect=capture_flag)
        mock_sdk_cls.return_value = mock_instance

        await bridge.new_session(cwd="/workspace")
        await bridge.cancel(session_id="s1")

        assert observed_cancelled == [True]

    @pytest.mark.asyncio
    @patch("protocol.acp.claude_bridge.ClaudeSDKClient")
    @patch("protocol.acp.claude_bridge.ClaudeAgentOptions")
    async def test_prompt_resets_cancelled_flag(
        self, _mock_options_cls, mock_sdk_cls, connected_bridge
    ):
        """prompt() resets _cancelled to False at the start."""
        from acp.schema import TextContentBlock

        mock_sdk_cls.return_value = make_sdk_mock()
        await connected_bridge.new_session(cwd="/workspace")

        # Simulate a prior cancel
        connected_bridge._cancelled = True

        prompt_blocks = [TextContentBlock(type="text", text="hello again")]
        result = await connected_bridge.prompt(prompt=prompt_blocks, session_id="s1")
        # Flag should be reset; since no cancel during streaming, stop is end_turn
        assert connected_bridge._cancelled is False
        assert result.stop_reason == "end_turn"

    @pytest.mark.asyncio
    @patch("protocol.acp.claude_bridge.ClaudeSDKClient")
    @patch("protocol.acp.claude_bridge.ClaudeAgentOptions")
    async def test_cancelled_during_streaming_returns_cancelled(
        self,
        _mock_options_cls,
        mock_sdk_cls,
        connected_bridge,
        mock_conn,  # noqa: ARG002
    ):
        """When _cancelled is set during streaming, stop_reason is 'cancelled'.

        We simulate this by setting the flag via a query() side_effect so it
        is True when the streaming loop starts (after prompt() resets it).
        """
        from acp.schema import TextContentBlock
        from claude_agent_sdk import AssistantMessage, TextBlock

        text_block = MagicMock(spec=TextBlock)
        text_block.text = "partial response"

        msg = MagicMock(spec=AssistantMessage)
        msg.content = [text_block]

        mock_client = make_sdk_mock(messages=[msg])

        # Set _cancelled DURING query() -- after prompt() resets it but before
        # the streaming loop reads it.
        async def _set_cancelled(*_args, **_kwargs):
            connected_bridge._cancelled = True

        mock_client.query = AsyncMock(side_effect=_set_cancelled)
        mock_sdk_cls.return_value = mock_client

        await connected_bridge.new_session(cwd="/workspace")

        prompt_blocks = [TextContentBlock(type="text", text="test")]
        result = await connected_bridge.prompt(prompt=prompt_blocks, session_id="s1")
        assert result.stop_reason == "cancelled"

    @pytest.mark.asyncio
    @patch("protocol.acp.claude_bridge.ClaudeSDKClient")
    @patch("protocol.acp.claude_bridge.ClaudeAgentOptions")
    async def test_cancelled_skips_emit_for_remaining_messages(
        self, _mock_options_cls, mock_sdk_cls, connected_bridge, mock_conn
    ):
        """When cancelled, remaining messages are NOT emitted via session_update.

        The loop breaks immediately so _emit_updates is never called for
        messages after the cancelled check.
        """
        from acp.schema import TextContentBlock
        from claude_agent_sdk import AssistantMessage, TextBlock

        text_block = MagicMock(spec=TextBlock)
        text_block.text = "should not be emitted"

        msg1 = MagicMock(spec=AssistantMessage)
        msg1.content = [text_block]

        msg2 = MagicMock(spec=AssistantMessage)
        msg2.content = [text_block]

        mock_client = make_sdk_mock(messages=[msg1, msg2])

        # Set _cancelled DURING query() so the streaming loop sees it
        async def _set_cancelled(*_args, **_kwargs):
            connected_bridge._cancelled = True

        mock_client.query = AsyncMock(side_effect=_set_cancelled)
        mock_sdk_cls.return_value = mock_client

        await connected_bridge.new_session(cwd="/workspace")

        prompt_blocks = [TextContentBlock(type="text", text="test")]
        await connected_bridge.prompt(prompt=prompt_blocks, session_id="s1")

        # Because cancelled is True when the loop starts, _emit_updates
        # is never called -- no session_update calls should be made.
        mock_conn.session_update.assert_not_called()

    @pytest.mark.asyncio
    @patch("protocol.acp.claude_bridge.ClaudeSDKClient")
    @patch("protocol.acp.claude_bridge.ClaudeAgentOptions")
    async def test_cancel_then_new_prompt_works_normally(
        self, _mock_options_cls, mock_sdk_cls, connected_bridge
    ):
        """After cancel, a subsequent prompt() resets and works normally."""
        from acp.schema import TextContentBlock

        mock_sdk_cls.return_value = make_sdk_mock()
        await connected_bridge.new_session(cwd="/workspace")

        # Cancel first
        await connected_bridge.cancel(session_id="s1")
        assert connected_bridge._cancelled is True

        # New prompt resets the flag and completes normally
        prompt_blocks = [TextContentBlock(type="text", text="continue")]
        result = await connected_bridge.prompt(prompt=prompt_blocks, session_id="s1")
        assert connected_bridge._cancelled is False
        assert result.stop_reason == "end_turn"


# ---------------------------------------------------------------------------
# TestGranularErrorHandling
# ---------------------------------------------------------------------------


class TestGranularErrorHandling:
    """Test granular error handling: warning logs for edge cases."""

    @pytest.mark.asyncio
    async def test_untracked_tool_id_logs_warning(
        self,
        connected_bridge,
        mock_conn,  # noqa: ARG002
        caplog,
    ):
        """UserMessage with tool_use_id not in _pending_tools triggers warning."""
        import logging

        from claude_agent_sdk import UserMessage

        msg = MagicMock(spec=UserMessage)
        msg.parent_tool_use_id = "toolu_orphan"
        msg.content = []

        with caplog.at_level(logging.WARNING, logger="protocol.acp.claude_bridge"):
            await connected_bridge._emit_user_message(msg, "s1")

        assert any("untracked" in record.message.lower() for record in caplog.records)
        assert any("toolu_orphan" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_untracked_tool_id_still_emits_update(
        self, connected_bridge, mock_conn
    ):
        """Even with an untracked tool_use_id, a ToolCallProgress is still emitted."""
        from acp.schema import ToolCallProgress
        from claude_agent_sdk import UserMessage

        msg = MagicMock(spec=UserMessage)
        msg.parent_tool_use_id = "toolu_untracked"
        msg.content = []

        await connected_bridge._emit_user_message(msg, "s1")

        mock_conn.session_update.assert_called_once()
        call_kwargs = mock_conn.session_update.call_args.kwargs
        update = call_kwargs["update"]
        assert isinstance(update, ToolCallProgress)
        assert update.tool_call_id == "toolu_untracked"
        assert update.title is None

    @pytest.mark.asyncio
    async def test_tracked_tool_id_no_warning(
        self,
        connected_bridge,
        mock_conn,  # noqa: ARG002
        caplog,
    ):
        """UserMessage with a tracked tool_use_id does NOT trigger warning."""
        import logging

        from claude_agent_sdk import UserMessage

        connected_bridge._pending_tools["toolu_tracked"] = "Read"

        msg = MagicMock(spec=UserMessage)
        msg.parent_tool_use_id = "toolu_tracked"
        msg.content = []

        with caplog.at_level(logging.WARNING, logger="protocol.acp.claude_bridge"):
            await connected_bridge._emit_user_message(msg, "s1")

        assert not any(
            "untracked" in record.message.lower() for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_unknown_block_type_logs_warning(
        self,
        connected_bridge,
        mock_conn,  # noqa: ARG002
        caplog,
    ):
        """Unsupported content block type in AssistantMessage triggers warning."""
        import logging

        from claude_agent_sdk import AssistantMessage

        unknown_block = MagicMock()  # Not TextBlock, ThinkingBlock, or ToolUseBlock

        msg = MagicMock(spec=AssistantMessage)
        msg.content = [unknown_block]

        with caplog.at_level(logging.WARNING, logger="protocol.acp.claude_bridge"):
            await connected_bridge._emit_assistant(msg, "s1")

        assert any("unsupported" in record.message.lower() for record in caplog.records)

    @pytest.mark.asyncio
    async def test_unknown_block_type_not_emitted(self, connected_bridge, mock_conn):
        """Unsupported content block type does not emit a session_update."""
        from claude_agent_sdk import AssistantMessage

        unknown_block = MagicMock()

        msg = MagicMock(spec=AssistantMessage)
        msg.content = [unknown_block]

        await connected_bridge._emit_assistant(msg, "s1")

        mock_conn.session_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_block_type_debug_extra_detail(self, mock_conn, caplog):
        """In debug mode, unknown block type also logs block details at DEBUG."""
        import logging

        bridge_dbg = ClaudeACPBridge(model="test", debug=True)
        bridge_dbg.on_connect(mock_conn)

        from claude_agent_sdk import AssistantMessage

        unknown_block = MagicMock()

        msg = MagicMock(spec=AssistantMessage)
        msg.content = [unknown_block]

        with caplog.at_level(logging.DEBUG, logger="protocol.acp.claude_bridge"):
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
        mock_conn,  # noqa: ARG002
        caplog,
    ):
        """In non-debug mode, unknown block type logs warning but not debug detail."""
        import logging

        from claude_agent_sdk import AssistantMessage

        unknown_block = MagicMock()

        msg = MagicMock(spec=AssistantMessage)
        msg.content = [unknown_block]

        with caplog.at_level(logging.DEBUG, logger="protocol.acp.claude_bridge"):
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
        mock_conn,  # noqa: ARG002
        caplog,
    ):
        """Warning log for unsupported block includes the block's class name."""
        import logging

        from claude_agent_sdk import AssistantMessage

        unknown_block = MagicMock()

        msg = MagicMock(spec=AssistantMessage)
        msg.content = [unknown_block]

        with caplog.at_level(logging.WARNING, logger="protocol.acp.claude_bridge"):
            await connected_bridge._emit_assistant(msg, "s1")

        # The warning should contain "MagicMock" (the class name)
        assert any("MagicMock" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_mixed_known_and_unknown_blocks(
        self, connected_bridge, mock_conn, caplog
    ):
        """Known blocks are emitted normally; unknown blocks trigger warning only."""
        import logging

        from claude_agent_sdk import AssistantMessage, TextBlock

        text_block = MagicMock(spec=TextBlock)
        text_block.text = "valid text"

        unknown_block = MagicMock()  # Unknown

        msg = MagicMock(spec=AssistantMessage)
        msg.content = [text_block, unknown_block]

        with caplog.at_level(logging.WARNING, logger="protocol.acp.claude_bridge"):
            await connected_bridge._emit_assistant(msg, "s1")

        # TextBlock should produce one session_update; unknown should not
        assert mock_conn.session_update.call_count == 1
        assert any("unsupported" in record.message.lower() for record in caplog.records)
