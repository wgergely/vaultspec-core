"""Streaming tests for ClaudeACPBridge.

Covers: prompt, _emit_updates, _emit_assistant, _emit_user_message,
_emit_system_message, _emit_result, _emit_stream_event.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from acp.schema import ContentToolCallContent, TextContentBlock
from claude_agent_sdk import (
    AssistantMessage,
    ContentBlock,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from tests.constants import TEST_PROJECT

from .. import ClaudeACPBridge
from ..claude_bridge import _map_tool_kind

if TYPE_CHECKING:
    from acp.schema import FileEditToolCallContent

from .conftest import (
    SDKClientRecorder,
    make_di_bridge,
    make_test_client,
    make_test_conn,
)

pytestmark = [pytest.mark.unit]


class _UnknownBlock:
    """Sentinel for testing unsupported content block types."""


class TestPrompt:
    """Test the prompt method."""

    @pytest.mark.asyncio
    async def test_raises_without_session(self):
        """prompt() raises RuntimeError if no session exists."""

        bridge, _holder, _captured = make_di_bridge()

        prompt_blocks = [TextContentBlock(type="text", text="hello")]
        with pytest.raises(RuntimeError, match="No active session"):
            await bridge.prompt(prompt=prompt_blocks, session_id="none")

    @pytest.mark.asyncio
    async def test_returns_prompt_response(self):
        """prompt() returns PromptResponse with stop_reason."""
        from acp.schema import PromptResponse

        bridge, _holder, _captured = make_di_bridge()
        bridge.on_connect(make_test_conn())

        await bridge.new_session(cwd=str(TEST_PROJECT))

        prompt_blocks = [TextContentBlock(type="text", text="hello")]
        result = await bridge.prompt(prompt=prompt_blocks, session_id="test")
        assert isinstance(result, PromptResponse)
        assert result.stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_calls_query_with_prompt_payload(self):
        """prompt() calls sdk_client.query() with a structured message payload."""

        test_client = make_test_client()
        bridge, _holder, _captured = make_di_bridge(client=test_client)
        bridge.on_connect(make_test_conn())

        await bridge.new_session(cwd=str(TEST_PROJECT))

        prompt_blocks = [TextContentBlock(type="text", text="Write a story")]
        await bridge.prompt(prompt=prompt_blocks, session_id="s1")

        assert len(test_client.query_calls) == 1
        # query() receives an async generator; recorder consumes it into a list
        payload = test_client.query_calls[0]
        assert len(payload) == 1
        msg = payload[0]
        assert msg["type"] == "user"
        assert msg["message"]["role"] == "user"
        text_parts = [
            c["text"] for c in msg["message"]["content"] if c["type"] == "text"
        ]
        assert text_parts == ["Write a story"]

    @pytest.mark.asyncio
    async def test_connects_in_new_session(self):
        """new_session() calls connect() to open the SDK connection."""
        test_client = make_test_client()
        bridge, _holder, _captured = make_di_bridge(client=test_client)
        bridge.on_connect(make_test_conn())

        await bridge.new_session(cwd=str(TEST_PROJECT))

        assert len(test_client.connect_calls) == 1

    @pytest.mark.asyncio
    async def test_error_result_sets_end_turn(self):
        """If ResultMessage.is_error is True, stop_reason is 'end_turn'."""

        error_msg = ResultMessage(
            subtype="result",
            duration_ms=0,
            duration_api_ms=0,
            is_error=True,
            num_turns=0,
            session_id="",
            result="Error occurred",
        )

        bridge, _holder, _captured = make_di_bridge(
            client=make_test_client(messages=[error_msg])
        )
        bridge.on_connect(make_test_conn())

        await bridge.new_session(cwd=str(TEST_PROJECT))

        prompt_blocks = [TextContentBlock(type="text", text="test")]
        result = await bridge.prompt(prompt=prompt_blocks, session_id="s1")
        assert result.stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_exception_sets_end_turn(self):
        """If streaming raises an exception, stop_reason is 'end_turn'."""

        test_client = SDKClientRecorder(stream_error=RuntimeError("stream failed"))
        bridge, _holder, _captured = make_di_bridge(client=test_client)
        bridge.on_connect(make_test_conn())

        await bridge.new_session(cwd=str(TEST_PROJECT))

        prompt_blocks = [TextContentBlock(type="text", text="test")]
        result = await bridge.prompt(prompt=prompt_blocks, session_id="s1")
        assert result.stop_reason == "end_turn"


class TestEmitUpdates:
    """Test the _emit_updates message router."""

    @pytest.mark.asyncio
    async def test_no_conn_does_nothing(self, bridge):
        """If _conn is None, _emit_updates does nothing."""
        msg = object()
        # Should not raise
        await bridge._emit_updates(msg, "s1")

    @pytest.mark.asyncio
    async def test_routes_assistant_message(self, connected_bridge, test_conn):
        """AssistantMessage is routed to _emit_assistant."""
        text_block = TextBlock(text="hello")
        msg = AssistantMessage(content=[text_block], model="test-model")

        await connected_bridge._emit_updates(msg, "s1")
        # TextBlock is skipped in _emit_assistant, so no update emitted
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_routes_user_message(self, connected_bridge, test_conn):
        """UserMessage is routed to _emit_user_message."""
        msg = UserMessage(parent_tool_use_id="toolu_1", content=[])

        await connected_bridge._emit_updates(msg, "s1")
        assert len(test_conn.session_update_calls) == 1

    @pytest.mark.asyncio
    async def test_routes_system_message(self, connected_bridge, test_conn):
        """SystemMessage is routed to _emit_system_message."""
        msg = SystemMessage(subtype="init", data={})

        await connected_bridge._emit_updates(msg, "s1")
        assert len(test_conn.session_update_calls) == 1

    @pytest.mark.asyncio
    async def test_routes_result_message(self, connected_bridge, test_conn):
        """ResultMessage is routed to _emit_result."""
        msg = ResultMessage(
            subtype="result",
            duration_ms=0,
            duration_api_ms=0,
            is_error=False,
            num_turns=0,
            session_id="",
            result="done",
        )

        await connected_bridge._emit_updates(msg, "s1")
        assert len(test_conn.session_update_calls) == 1

    @pytest.mark.asyncio
    async def test_routes_stream_event(self, connected_bridge, test_conn):
        """StreamEvent is routed to _emit_stream_event."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="u1",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "hi"},
            },
        )

        await connected_bridge._emit_updates(msg, "s1")
        assert len(test_conn.session_update_calls) == 1

    @pytest.mark.asyncio
    async def test_stream_event_dispatched_before_assistant(
        self, connected_bridge, test_conn
    ):
        """StreamEvent check comes before AssistantMessage in _emit_updates."""
        from acp.schema import AgentMessageChunk
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="u1",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "delta"},
            },
        )

        await connected_bridge._emit_updates(msg, "s1")

        assert len(test_conn.session_update_calls) == 1
        call_kwargs = test_conn.session_update_calls[-1]
        assert isinstance(call_kwargs["update"], AgentMessageChunk)

    @pytest.mark.asyncio
    async def test_unknown_message_debug_log(self, test_conn):
        """Unknown message type is logged in debug mode."""
        bridge_dbg = ClaudeACPBridge(model="test", debug=True)
        bridge_dbg.on_connect(test_conn)

        msg = object()  # Not a known SDK type
        await bridge_dbg._emit_updates(msg, "s1")
        assert len(test_conn.session_update_calls) == 0


class TestEmitAssistant:
    """Test _emit_assistant maps content blocks to session_update calls."""

    @pytest.mark.asyncio
    async def test_text_block_skipped_in_assistant_message(
        self, connected_bridge, test_conn
    ):
        """A TextBlock in AssistantMessage is skipped (streamed earlier)."""
        text_block = TextBlock(text="Hello from Claude")
        msg = AssistantMessage(content=[text_block], model="test-model")

        await connected_bridge._emit_assistant(msg, "s1")

        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_thinking_block_skipped_in_assistant_message(
        self, connected_bridge, test_conn
    ):
        """A ThinkingBlock in AssistantMessage is skipped (streamed earlier)."""
        thinking_block = ThinkingBlock(thinking="Let me analyze...", signature="")
        msg = AssistantMessage(content=[thinking_block], model="test-model")

        await connected_bridge._emit_assistant(msg, "s1")

        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_tool_use_block_emits_tool_call_start(
        self, connected_bridge, test_conn
    ):
        """A ToolUseBlock triggers session_update with ToolCallStart."""
        from acp.schema import ToolCallStart

        tool_block = ToolUseBlock(id="toolu_123", name="Read", input={})
        msg = AssistantMessage(content=[tool_block], model="test-model")

        await connected_bridge._emit_assistant(msg, "s1")

        assert len(test_conn.session_update_calls) == 1
        call_kwargs = test_conn.session_update_calls[-1]
        update = call_kwargs["update"]
        assert isinstance(update, ToolCallStart)
        assert update.tool_call_id == "toolu_123"
        assert update.title == "Read"
        assert update.status == "pending"

    @pytest.mark.asyncio
    async def test_tool_use_block_caches_pending_tool(
        self,
        connected_bridge,
        test_conn,
    ):
        """A ToolUseBlock caches tool_call_id -> tool_name in _pending_tools."""
        tool_block = ToolUseBlock(id="toolu_cache_test", name="Write", input={})
        msg = AssistantMessage(content=[tool_block], model="test-model")

        await connected_bridge._emit_assistant(msg, "s1")

        assert connected_bridge._pending_tools["toolu_cache_test"] == "Write"

    @pytest.mark.asyncio
    async def test_multiple_blocks_skip_text_emit_tool(
        self, connected_bridge, test_conn
    ):
        """Multiple content blocks: TextBlock skipped, ToolUseBlock emitted."""
        text_block = TextBlock(text="Reading file...")
        tool_block = ToolUseBlock(id="toolu_456", name="Bash", input={})
        msg = AssistantMessage(content=[text_block, tool_block], model="test-model")

        await connected_bridge._emit_assistant(msg, "s1")

        assert len(test_conn.session_update_calls) == 1

    @pytest.mark.asyncio
    async def test_unknown_block_type_skipped(self, connected_bridge, test_conn):
        """Unknown block types are skipped (not emitted via session_update)."""
        unknown_block = _UnknownBlock()
        msg = AssistantMessage(
            content=cast("list[ContentBlock]", [unknown_block]),
            model="test-model",
        )

        await connected_bridge._emit_assistant(msg, "s1")
        assert len(test_conn.session_update_calls) == 0


class TestEmitUserMessage:
    """Test _emit_user_message maps UserMessage to ToolCallProgress."""

    @pytest.mark.asyncio
    async def test_user_message_with_tool_id(self, connected_bridge, test_conn):
        """UserMessage with parent_tool_use_id emits ToolCallProgress."""
        from acp.schema import ToolCallProgress

        msg = UserMessage(parent_tool_use_id="toolu_789", content=[])

        await connected_bridge._emit_user_message(msg, "s1")

        assert len(test_conn.session_update_calls) == 1
        call_kwargs = test_conn.session_update_calls[-1]
        update = call_kwargs["update"]
        assert isinstance(update, ToolCallProgress)
        assert update.tool_call_id == "toolu_789"
        assert update.status == "completed"

    @pytest.mark.asyncio
    async def test_user_message_no_tool_id(self, connected_bridge, test_conn):
        """UserMessage without parent_tool_use_id does not emit."""
        msg = UserMessage(parent_tool_use_id=None, content=[])

        await connected_bridge._emit_user_message(msg, "s1")
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_user_message_empty_tool_id(self, connected_bridge, test_conn):
        """UserMessage with empty parent_tool_use_id does not emit."""
        msg = UserMessage(parent_tool_use_id="", content=[])

        await connected_bridge._emit_user_message(msg, "s1")
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_user_message_correlates_pending_tool(
        self, connected_bridge, test_conn
    ):
        """UserMessage pops from _pending_tools to set title on ToolCallProgress."""
        # Pre-populate the pending tools cache (as _emit_assistant would)
        connected_bridge._pending_tools["toolu_corr"] = "Bash"

        msg = UserMessage(parent_tool_use_id="toolu_corr", content=[])

        await connected_bridge._emit_user_message(msg, "s1")

        call_kwargs = test_conn.session_update_calls[-1]
        assert call_kwargs["update"].title == "Bash"
        # Should be popped from cache
        assert "toolu_corr" not in connected_bridge._pending_tools

    @pytest.mark.asyncio
    async def test_user_message_unknown_tool_id_title_none(
        self, connected_bridge, test_conn
    ):
        """UserMessage with tool_id not in _pending_tools gets title=None."""
        msg = UserMessage(parent_tool_use_id="toolu_unknown", content=[])

        await connected_bridge._emit_user_message(msg, "s1")

        call_kwargs = test_conn.session_update_calls[-1]
        assert call_kwargs["update"].title is None

    @pytest.mark.asyncio
    async def test_user_message_error_result_sets_failed(
        self, connected_bridge, test_conn
    ):
        """UserMessage with ToolResultBlock.is_error=True sets status='failed'."""
        error_block = ToolResultBlock(tool_use_id="", is_error=True)
        msg = UserMessage(parent_tool_use_id="toolu_err", content=[error_block])

        await connected_bridge._emit_user_message(msg, "s1")

        call_kwargs = test_conn.session_update_calls[-1]
        assert call_kwargs["update"].status == "failed"

    @pytest.mark.asyncio
    async def test_user_message_success_result_sets_completed(
        self, connected_bridge, test_conn
    ):
        """UserMessage with ToolResultBlock.is_error=False keeps status='completed'."""
        ok_block = ToolResultBlock(tool_use_id="", is_error=False)
        msg = UserMessage(parent_tool_use_id="toolu_ok", content=[ok_block])

        await connected_bridge._emit_user_message(msg, "s1")

        call_kwargs = test_conn.session_update_calls[-1]
        assert call_kwargs["update"].status == "completed"


class TestEmitSystemMessage:
    """Test _emit_system_message maps SystemMessage to SessionInfoUpdate."""

    @pytest.mark.asyncio
    async def test_system_message_emits_session_info(self, connected_bridge, test_conn):
        """SystemMessage emits SessionInfoUpdate with title from subtype."""
        from acp.schema import SessionInfoUpdate

        msg = SystemMessage(subtype="init", data={})

        await connected_bridge._emit_system_message(msg, "s1")

        assert len(test_conn.session_update_calls) == 1
        call_kwargs = test_conn.session_update_calls[-1]
        update = call_kwargs["update"]
        assert isinstance(update, SessionInfoUpdate)
        assert update.title == "init"

    @pytest.mark.asyncio
    async def test_system_message_missing_subtype(self, connected_bridge, test_conn):
        """SystemMessage without subtype attr defaults to 'system'."""
        msg = SystemMessage(subtype="system", data={})
        del msg.subtype  # Simulate missing attribute

        await connected_bridge._emit_system_message(msg, "s1")

        call_kwargs = test_conn.session_update_calls[-1]
        assert call_kwargs["update"].title == "system"


class TestEmitResult:
    """Test _emit_result maps ResultMessage to SessionInfoUpdate."""

    @pytest.mark.asyncio
    async def test_result_with_text(self, connected_bridge, test_conn):
        """ResultMessage with text emits SessionInfoUpdate with truncated title."""
        from acp.schema import SessionInfoUpdate

        msg = ResultMessage(
            subtype="result",
            duration_ms=0,
            duration_api_ms=0,
            is_error=False,
            num_turns=0,
            session_id="",
            result="Task completed successfully.",
        )

        await connected_bridge._emit_result(msg, "s1")

        call_kwargs = test_conn.session_update_calls[-1]
        update = call_kwargs["update"]
        assert isinstance(update, SessionInfoUpdate)
        assert "Task completed" in update.title

    @pytest.mark.asyncio
    async def test_result_empty(self, connected_bridge, test_conn):
        """ResultMessage with no result text emits 'Result' title."""
        msg = ResultMessage(
            subtype="result",
            duration_ms=0,
            duration_api_ms=0,
            is_error=False,
            num_turns=0,
            session_id="",
            result=None,
        )

        await connected_bridge._emit_result(msg, "s1")

        call_kwargs = test_conn.session_update_calls[-1]
        assert call_kwargs["update"].title == "Result"

    @pytest.mark.asyncio
    async def test_result_long_text_truncated(self, connected_bridge, test_conn):
        """ResultMessage with very long text has title truncated to 100 chars."""
        msg = ResultMessage(
            subtype="result",
            duration_ms=0,
            duration_api_ms=0,
            is_error=False,
            num_turns=0,
            session_id="",
            result="x" * 500,
        )

        await connected_bridge._emit_result(msg, "s1")

        call_kwargs = test_conn.session_update_calls[-1]
        title = call_kwargs["update"].title
        # "Result: " + 100 chars of 'x'
        assert len(title) <= len("Result: ") + 100

    @pytest.mark.asyncio
    async def test_result_non_string(self, connected_bridge, test_conn):
        """ResultMessage with non-string result is str()-converted."""
        # ResultMessage requires result to be str | None, so pass as str
        msg = ResultMessage(
            subtype="result",
            duration_ms=0,
            duration_api_ms=0,
            is_error=False,
            num_turns=0,
            session_id="",
            result="{'key': 'value'}",
        )

        await connected_bridge._emit_result(msg, "s1")

        call_kwargs = test_conn.session_update_calls[-1]
        assert "Result:" in call_kwargs["update"].title


class TestEmitStreamEvent:
    """Test _emit_stream_event maps StreamEvent deltas to ACP chunks."""

    @pytest.mark.asyncio
    async def test_text_delta_emits_agent_message_chunk(
        self, connected_bridge, test_conn
    ):
        """A content_block_delta with text_delta emits AgentMessageChunk."""
        from acp.schema import AgentMessageChunk
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="evt-1",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "Hello, world!"},
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")

        assert len(test_conn.session_update_calls) == 1
        call_kwargs = test_conn.session_update_calls[-1]
        assert call_kwargs["session_id"] == "s1"
        update = call_kwargs["update"]
        assert isinstance(update, AgentMessageChunk)
        assert update.content.text == "Hello, world!"

    @pytest.mark.asyncio
    async def test_thinking_delta_emits_agent_thought_chunk(
        self, connected_bridge, test_conn
    ):
        """A content_block_delta with thinking_delta emits AgentThoughtChunk."""
        from acp.schema import AgentThoughtChunk
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="evt-2",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "delta": {"type": "thinking_delta", "thinking": "Let me consider..."},
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")

        assert len(test_conn.session_update_calls) == 1
        call_kwargs = test_conn.session_update_calls[-1]
        update = call_kwargs["update"]
        assert isinstance(update, AgentThoughtChunk)
        assert update.content.text == "Let me consider..."

    @pytest.mark.asyncio
    async def test_empty_text_delta_not_emitted(self, connected_bridge, test_conn):
        """A text_delta with empty text does not emit."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="evt-3",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": ""},
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_empty_thinking_delta_not_emitted(self, connected_bridge, test_conn):
        """A thinking_delta with empty thinking does not emit."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="evt-4",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "delta": {"type": "thinking_delta", "thinking": ""},
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_unknown_delta_type_no_emit(self, connected_bridge, test_conn):
        """An unknown delta type does not emit a session_update."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="evt-5",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "delta": {"type": "signature_delta", "signature": "abc123"},
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_non_delta_event_type_no_emit(self, connected_bridge, test_conn):
        """Non-content_block_delta event types do not emit."""
        from claude_agent_sdk.types import StreamEvent

        for event_type in [
            "content_block_start",
            "content_block_stop",
            "message_start",
        ]:
            test_conn.session_update_calls.clear()
            msg = StreamEvent(
                uuid="evt-6",
                session_id="s1",
                event={"type": event_type},
            )
            await connected_bridge._emit_stream_event(msg, "s1")
            assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_stream_event_routed_from_emit_updates(
        self, connected_bridge, test_conn
    ):
        """StreamEvent is correctly routed through _emit_updates."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="evt-7",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "routed"},
            },
        )

        await connected_bridge._emit_updates(msg, "s1")
        assert len(test_conn.session_update_calls) == 1
        assert test_conn.session_update_calls[-1]["update"].content.text == "routed"

    @pytest.mark.asyncio
    async def test_stream_event_checked_before_assistant_message(
        self, connected_bridge, test_conn
    ):
        """StreamEvent is checked before AssistantMessage in _emit_updates."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="evt-8",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "delta first"},
            },
        )

        await connected_bridge._emit_updates(msg, "s1")
        assert len(test_conn.session_update_calls) == 1

    @pytest.mark.asyncio
    async def test_missing_delta_key_no_crash(self, connected_bridge, test_conn):
        """Event with type=content_block_delta but no delta key doesn't crash."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="evt-9",
            session_id="s1",
            event={"type": "content_block_delta"},
        )

        await connected_bridge._emit_stream_event(msg, "s1")
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_empty_event_dict_no_crash(self, connected_bridge, test_conn):
        """Event with empty dict doesn't crash."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="evt-10",
            session_id="s1",
            event={},
        )

        await connected_bridge._emit_stream_event(msg, "s1")
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_missing_text_key_skipped(self, connected_bridge, test_conn):
        """text_delta without 'text' key does not emit (defaults to empty)."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="u1",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "delta": {"type": "text_delta"},
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_unknown_delta_type_debug_log(self, test_conn, caplog):
        """Unknown delta type logs at DEBUG level in debug mode."""
        import logging

        from claude_agent_sdk.types import StreamEvent

        bridge_dbg = ClaudeACPBridge(model="test", debug=True)
        bridge_dbg.on_connect(test_conn)

        msg = StreamEvent(
            uuid="u1",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "delta": {"type": "signature_delta", "signature": "abc123"},
            },
        )

        with caplog.at_level(
            logging.DEBUG, logger="vaultspec.protocol.acp.claude_bridge"
        ):
            await bridge_dbg._emit_stream_event(msg, "s1")

        assert any("signature_delta" in record.message for record in caplog.records)
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_unknown_event_type_debug_log(self, test_conn, caplog):
        """Unknown event type logs at DEBUG level in debug mode."""
        import logging

        from claude_agent_sdk.types import StreamEvent

        bridge_dbg = ClaudeACPBridge(model="test", debug=True)
        bridge_dbg.on_connect(test_conn)

        msg = StreamEvent(
            uuid="u1",
            session_id="s1",
            event={"type": "message_start"},
        )

        with caplog.at_level(
            logging.DEBUG, logger="vaultspec.protocol.acp.claude_bridge"
        ):
            await bridge_dbg._emit_stream_event(msg, "s1")

        assert any("message_start" in record.message for record in caplog.records)
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_missing_event_type_not_emitted(self, connected_bridge, test_conn):
        """Event dict without 'type' key does not emit."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="u1",
            session_id="s1",
            event={"data": "something"},
        )

        await connected_bridge._emit_stream_event(msg, "s1")
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_text_delta_preserves_whitespace(self, connected_bridge, test_conn):
        """text_delta with whitespace-only text is still emitted (non-empty)."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="u1",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "  \n  "},
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")
        assert len(test_conn.session_update_calls) == 1
        call_kwargs = test_conn.session_update_calls[-1]
        assert call_kwargs["update"].content.text == "  \n  "


class TestContentBlockStartTracking:
    """Test content_block_start event tracking for tool_use correlation."""

    @pytest.mark.asyncio
    async def test_tool_use_block_start_records_index(
        self, connected_bridge, test_conn
    ):
        """content_block_start with tool_use records index -> tool_call_id."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="cbs-1",
            session_id="s1",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_abc123",
                    "name": "Read",
                },
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")
        assert connected_bridge._block_index_to_tool[0] == "toolu_abc123"
        # content_block_start should not emit session_update
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_non_tool_use_block_start_not_tracked(
        self, connected_bridge, test_conn
    ):
        """content_block_start with type=text does not track index."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="cbs-2",
            session_id="s1",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")
        assert 0 not in connected_bridge._block_index_to_tool
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_multiple_tool_blocks_tracked(
        self,
        connected_bridge,
        test_conn,
    ):
        """Multiple tool_use content blocks track their respective indices."""
        from claude_agent_sdk.types import StreamEvent

        for i, tool_id in [(1, "toolu_first"), (3, "toolu_second")]:
            msg = StreamEvent(
                uuid=f"cbs-{i}",
                session_id="s1",
                event={
                    "type": "content_block_start",
                    "index": i,
                    "content_block": {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": f"Tool{i}",
                    },
                },
            )
            await connected_bridge._emit_stream_event(msg, "s1")

        assert connected_bridge._block_index_to_tool[1] == "toolu_first"
        assert connected_bridge._block_index_to_tool[3] == "toolu_second"

    @pytest.mark.asyncio
    async def test_missing_index_not_tracked(
        self,
        connected_bridge,
        test_conn,
    ):
        """content_block_start without index does not track."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="cbs-3",
            session_id="s1",
            event={
                "type": "content_block_start",
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_no_idx",
                    "name": "Read",
                },
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")
        assert len(connected_bridge._block_index_to_tool) == 0

    @pytest.mark.asyncio
    async def test_missing_tool_id_not_tracked(
        self,
        connected_bridge,
        test_conn,
    ):
        """content_block_start with tool_use but empty id does not track."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="cbs-4",
            session_id="s1",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "",
                    "name": "Read",
                },
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")
        assert 0 not in connected_bridge._block_index_to_tool


class TestInputJsonDelta:
    """Test input_json_delta handling for streaming tool arguments."""

    @pytest.mark.asyncio
    async def test_input_json_delta_emits_tool_call_progress(
        self, connected_bridge, test_conn
    ):
        """input_json_delta emits ToolCallProgress with partial args."""
        from acp.schema import ToolCallProgress
        from claude_agent_sdk.types import StreamEvent

        # Set up block index tracking and pending tools
        connected_bridge._block_index_to_tool[0] = "toolu_abc"
        connected_bridge._pending_tools["toolu_abc"] = "Read"

        msg = StreamEvent(
            uuid="ijd-1",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": '{"file_path":'},
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")

        assert len(test_conn.session_update_calls) == 1
        call_kwargs = test_conn.session_update_calls[-1]
        update = call_kwargs["update"]
        assert isinstance(update, ToolCallProgress)
        assert update.tool_call_id == "toolu_abc"
        assert update.title == "Read"
        assert update.status == "in_progress"
        assert update.raw_input == '{"file_path":'

    @pytest.mark.asyncio
    async def test_input_json_delta_without_tracking(self, connected_bridge, test_conn):
        """input_json_delta without block tracking emits with empty tool_call_id."""
        from acp.schema import ToolCallProgress
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="ijd-2",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "index": 5,
                "delta": {"type": "input_json_delta", "partial_json": '{"key":'},
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")

        assert len(test_conn.session_update_calls) == 1
        update = test_conn.session_update_calls[-1]["update"]
        assert isinstance(update, ToolCallProgress)
        assert update.tool_call_id == ""
        assert update.title is None

    @pytest.mark.asyncio
    async def test_input_json_delta_empty_partial_not_emitted(
        self, connected_bridge, test_conn
    ):
        """input_json_delta with empty partial_json does not emit."""
        from claude_agent_sdk.types import StreamEvent

        msg = StreamEvent(
            uuid="ijd-3",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": ""},
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")
        assert len(test_conn.session_update_calls) == 0

    @pytest.mark.asyncio
    async def test_input_json_delta_multiple_chunks(self, connected_bridge, test_conn):
        """Multiple input_json_delta chunks emit multiple ToolCallProgress updates."""
        from claude_agent_sdk.types import StreamEvent

        connected_bridge._block_index_to_tool[0] = "toolu_multi"
        connected_bridge._pending_tools["toolu_multi"] = "Write"

        chunks = ['{"file_path":', '"test.md"', ',"content":', '"hello"}']
        for i, chunk in enumerate(chunks):
            msg = StreamEvent(
                uuid=f"ijd-m{i}",
                session_id="s1",
                event={
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "input_json_delta", "partial_json": chunk},
                },
            )
            await connected_bridge._emit_stream_event(msg, "s1")

        assert len(test_conn.session_update_calls) == 4
        last_update = test_conn.session_update_calls[-1]["update"]
        assert last_update.raw_input == '"hello"}'

    @pytest.mark.asyncio
    async def test_full_tool_use_streaming_flow(self, connected_bridge, test_conn):
        """Full flow: content_block_start -> input_json_delta -> correlation."""
        from acp.schema import ToolCallProgress
        from claude_agent_sdk.types import StreamEvent

        # Step 1: ToolUseBlock in AssistantMessage caches pending tool
        tool_block = ToolUseBlock(id="toolu_flow", name="Bash", input={})
        assistant_msg = AssistantMessage(content=[tool_block], model="test-model")
        await connected_bridge._emit_assistant(assistant_msg, "s1")
        test_conn.session_update_calls.clear()

        # Step 2: content_block_start tracks index
        start_event = StreamEvent(
            uuid="flow-1",
            session_id="s1",
            event={
                "type": "content_block_start",
                "index": 2,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_flow",
                    "name": "Bash",
                },
            },
        )
        await connected_bridge._emit_stream_event(start_event, "s1")
        assert connected_bridge._block_index_to_tool[2] == "toolu_flow"

        # Step 3: input_json_delta correlates via index lookup
        delta_event = StreamEvent(
            uuid="flow-2",
            session_id="s1",
            event={
                "type": "content_block_delta",
                "index": 2,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": '{"command":"ls"}',
                },
            },
        )
        await connected_bridge._emit_stream_event(delta_event, "s1")

        assert len(test_conn.session_update_calls) == 1
        update = test_conn.session_update_calls[-1]["update"]
        assert isinstance(update, ToolCallProgress)
        assert update.tool_call_id == "toolu_flow"
        assert update.title == "Bash"
        assert update.status == "in_progress"
        assert update.raw_input == '{"command":"ls"}'


class TestTodoWritePlan:
    """Test TodoWrite-to-Plan conversion."""

    @pytest.mark.asyncio
    async def test_emit_assistant_intercepts_todo_write(
        self, connected_bridge, test_conn
    ):
        """AssistantMessage with TodoWrite tool use emits AgentPlanUpdate."""
        from acp.schema import AgentPlanUpdate, ToolCallStart

        from ..claude_bridge import _SessionState

        # Setup session state
        connected_bridge._sessions["s1"] = _SessionState(
            session_id="s1",
            cwd="/tmp",
            model="test",
            mode="read-write",
            mcp_servers=[],
            created_at="now",
        )

        todos = [{"content": "Fix bug", "status": "pending", "priority": "high"}]
        tool_block = ToolUseBlock(
            id="toolu_plan",
            name="TodoWrite",
            input={"todos": todos},
        )
        msg = AssistantMessage(content=[tool_block], model="test-model")

        await connected_bridge._emit_assistant(msg, "s1")

        # Verify plan update emitted
        assert len(test_conn.session_update_calls) == 1
        update = test_conn.session_update_calls[0]["update"]
        assert isinstance(update, AgentPlanUpdate)
        assert len(update.entries) == 1
        assert update.entries[0].content == "Fix bug"
        assert update.entries[0].status == "pending"

        # Verify tool call ID tracked
        session_state = connected_bridge._sessions.get("s1")
        assert "toolu_plan" in session_state.todo_write_tool_call_ids

        # Verify no ToolCallStart emitted
        assert not any(
            isinstance(call["update"], ToolCallStart)
            for call in test_conn.session_update_calls
        )

    @pytest.mark.asyncio
    async def test_emit_stream_event_intercepts_todo_write(
        self, connected_bridge, test_conn
    ):
        """StreamEvent with TodoWrite content_block_start emits AgentPlanUpdate."""
        from acp.schema import AgentPlanUpdate
        from claude_agent_sdk.types import StreamEvent

        from ..claude_bridge import _SessionState

        # Setup session state
        connected_bridge._sessions["s1"] = _SessionState(
            session_id="s1",
            cwd="/tmp",
            model="test",
            mode="read-write",
            mcp_servers=[],
            created_at="now",
        )

        todos = [{"content": "Refactor", "status": "completed"}]
        msg = StreamEvent(
            uuid="evt-plan",
            session_id="s1",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_stream_plan",
                    "name": "TodoWrite",
                    "input": {"todos": todos},
                },
            },
        )

        await connected_bridge._emit_stream_event(msg, "s1")

        assert len(test_conn.session_update_calls) == 1
        update = test_conn.session_update_calls[0]["update"]
        assert isinstance(update, AgentPlanUpdate)
        assert update.entries[0].content == "Refactor"

        session_state = connected_bridge._sessions.get("s1")
        assert "toolu_stream_plan" in session_state.todo_write_tool_call_ids

    @pytest.mark.asyncio
    async def test_emit_user_message_suppresses_todo_write(
        self, connected_bridge, test_conn
    ):
        """UserMessage for TodoWrite does not emit ToolCallProgress."""
        from ..claude_bridge import _SessionState

        # Setup session state with tracked ID
        session_state = _SessionState(
            session_id="s1",
            cwd="/tmp",
            model="test",
            mode="read-write",
            mcp_servers=[],
            created_at="now",
        )
        session_state.todo_write_tool_call_ids.add("toolu_suppress")
        connected_bridge._sessions["s1"] = session_state

        msg = UserMessage(parent_tool_use_id="toolu_suppress", content=[])

        await connected_bridge._emit_user_message(msg, "s1")

        assert len(test_conn.session_update_calls) == 0


class TestContentAccumulation:
    """Test tool content accumulation and kind mapping."""

    @pytest.mark.asyncio
    async def test_emit_assistant_accumulates_content(
        self, connected_bridge, test_conn
    ):
        """AssistantMessage initializes content in state."""
        from acp.schema import ToolCallStart

        from ..claude_bridge import _SessionState

        # Setup session state
        connected_bridge._sessions["s1"] = _SessionState(
            session_id="s1",
            cwd="/tmp",
            model="test",
            mode="read-write",
            mcp_servers=[],
            created_at="now",
        )

        # Edit tool should produce diff content
        input_data = {
            "file_path": "test.txt",
            "old_string": "foo",
            "new_string": "bar",
        }
        tool_block = ToolUseBlock(id="toolu_edit", name="Edit", input=input_data)
        msg = AssistantMessage(content=[tool_block], model="test-model")

        await connected_bridge._emit_assistant(msg, "s1")

        # Check state
        session_state = connected_bridge._sessions.get("s1")
        assert "toolu_edit" in session_state.tool_call_contents
        content = session_state.tool_call_contents["toolu_edit"]
        assert len(content) == 1
        assert cast("FileEditToolCallContent", content[0]).type == "diff"

        # Check update
        update = test_conn.session_update_calls[0]["update"]
        assert isinstance(update, ToolCallStart)
        assert update.kind == "edit"  # mapped from "Edit"
        # Convert Pydantic models to dicts for comparison
        update_content = [
            c.model_dump(by_alias=True, exclude_none=True) for c in update.content
        ]
        stored_content = [
            c.model_dump(by_alias=True, exclude_none=True) for c in content
        ]
        assert update_content == stored_content
        assert update.raw_input == input_data

    @pytest.mark.asyncio
    async def test_emit_user_message_accumulates_result(
        self, connected_bridge, test_conn
    ):
        """UserMessage appends result text to content."""
        from acp.schema import ToolCallProgress

        from ..claude_bridge import _SessionState

        # Setup session state
        session_state = _SessionState(
            session_id="s1",
            cwd="/tmp",
            model="test",
            mode="read-write",
            mcp_servers=[],
            created_at="now",
        )
        # Pre-populate state as if ToolCallStart happened
        from acp.schema import ContentToolCallContent

        session_state.tool_call_contents["toolu_res"] = [
            ContentToolCallContent(
                type="content",
                content=TextContentBlock(type="text", text="initial"),
            )
        ]
        connected_bridge._sessions["s1"] = session_state
        connected_bridge._pending_tools["toolu_res"] = "Bash"

        result_block = ToolResultBlock(
            tool_use_id="toolu_res", content="output", is_error=False
        )
        msg = UserMessage(parent_tool_use_id="toolu_res", content=[result_block])

        await connected_bridge._emit_user_message(msg, "s1")

        # Check state accumulation
        content = session_state.tool_call_contents["toolu_res"]
        assert len(content) == 2
        # Cast to check attributes on union type
        assert cast("ContentToolCallContent", content[1]).content.text == "output"

        # Check update
        update = test_conn.session_update_calls[0]["update"]
        assert isinstance(update, ToolCallProgress)
        # Convert Pydantic models to dicts for comparison
        update_content = []
        if update.content:
            for c in update.content:
                d = c.model_dump(by_alias=True, exclude_none=True)
                # Normalize nested TextContentBlock if needed
                if "content" in d and isinstance(d["content"], dict):
                    pass
                update_content.append(d)

        # Simplified check for content structure match
        assert len(update_content) == 2
        assert update_content[0]["type"] == "content"
        assert update_content[0]["content"]["text"] == "initial"
        assert update_content[1]["type"] == "content"
        assert update_content[1]["content"]["text"] == "output"
        assert update_content[0]["content"]["text"] == "initial"
        assert update_content[1]["type"] == "content"
        assert update_content[1]["content"]["text"] == "output"

        assert update.raw_output == {"output": "output"}


class TestToolKindMapping:
    """Test _map_tool_kind() maps tool names to ACP kinds via substring matching."""

    @pytest.mark.parametrize(
        ("tool_name", "expected_kind"),
        [
            # read
            ("Read", "read"),
            ("ReadFile", "read"),
            ("View", "read"),
            ("GetConfig", "read"),
            # edit
            ("Write", "edit"),
            ("CreateFile", "edit"),
            ("Update", "edit"),
            ("Edit", "edit"),
            ("MultiEdit", "edit"),
            # delete
            ("Delete", "delete"),
            ("Remove", "delete"),
            # move
            ("Move", "move"),
            ("Rename", "move"),
            # search
            ("Search", "search"),
            ("Find", "search"),
            ("Grep", "search"),
            # execute
            ("Run", "execute"),
            ("Execute", "execute"),
            ("Bash", "execute"),
            # think
            ("Think", "think"),
            ("Plan", "think"),
            # fetch
            ("Fetch", "fetch"),
            ("Download", "fetch"),
            ("WebFetch", "fetch"),
            # other
            ("UnknownTool", "other"),
            ("CustomAction", "other"),
        ],
    )
    def test_maps_tool_to_kind(self, tool_name, expected_kind):
        """_map_tool_kind maps tool names to expected ACP kinds."""
        assert _map_tool_kind(tool_name) == expected_kind

    def test_case_insensitive(self):
        """_map_tool_kind is case-insensitive."""
        assert _map_tool_kind("READ") == "read"
        assert _map_tool_kind("bash") == "execute"
        assert _map_tool_kind("WebFETCH") == "fetch"

    def test_first_match_wins(self):
        """When multiple keywords match, the first in priority order wins."""
        # "ReadWrite" contains both "read" and "write" — "read" comes first
        assert _map_tool_kind("ReadWrite") == "read"
