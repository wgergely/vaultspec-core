"""Unit tests for ClaudeA2AExecutor.

Mocks ClaudeSDKClient so no API key is needed. Validates execute,
error handling, cancel flow, and sandbox callback application.
"""

from __future__ import annotations

from typing import Any

import pytest
from a2a.server.events import EventQueue
from a2a.types import TaskState, TaskStatusUpdateEvent

from protocol.a2a.tests.conftest import make_request_context

SDK_MODULE = "protocol.a2a.executors.claude_executor"


# ---------------------------------------------------------------------------
# Helpers: fake SDK types
# ---------------------------------------------------------------------------


class _FakeTextBlock:
    """Stand-in for claude_agent_sdk.TextBlock."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeAssistantMessage:
    """Stand-in for claude_agent_sdk.AssistantMessage."""

    def __init__(self, blocks: list[_FakeTextBlock]) -> None:
        self.content = blocks


class _FakeResultMessage:
    """Stand-in for claude_agent_sdk.ResultMessage."""

    def __init__(self, *, result: str | None = None, is_error: bool = False) -> None:
        self.result = result
        self.is_error = is_error


async def _async_iter(items: list[Any]):
    """Yield items as an async iterator."""
    for item in items:
        yield item


def _drain_events(queue: EventQueue) -> list[Any]:
    """Drain all events from an EventQueue, calling task_done() for each."""
    events = []
    while not queue.queue.empty():
        events.append(queue.queue.get_nowait())
        queue.task_done()
    return events


class _AwaitableNone:
    """Object that can be awaited (returns None)."""

    def __await__(self):
        return iter([])


class _FakeSDKClient:
    """Fake ClaudeSDKClient for tests.

    disconnect() is callable both sync and async: it returns an awaitable
    so ``await client.disconnect()`` works, but also increments the counter
    when called without await (as the cancel path does).
    """

    def __init__(self, messages=None, connect_error=None):
        self.messages = messages or []
        self.connect_error = connect_error
        self.connect_calls: list[tuple] = []
        self.query_calls: list[str] = []
        self.disconnect_calls: int = 0
        self.interrupt_calls: int = 0

    async def connect(self, *args, **kwargs):
        self.connect_calls.append((args, kwargs))
        if self.connect_error:
            raise self.connect_error

    async def query(self, prompt: str):
        self.query_calls.append(prompt)

    def disconnect(self):
        self.disconnect_calls += 1
        return _AwaitableNone()

    def interrupt(self):
        self.interrupt_calls += 1

    def receive_messages(self):
        return _async_iter(self.messages)


class _OptionsRecorder:
    """Records kwargs passed to ClaudeAgentOptions constructor."""

    last_call: dict | None = None

    def __init__(self, **kwargs):
        _OptionsRecorder.last_call = kwargs

    @classmethod
    def reset(cls):
        cls.last_call = None


def _patch_sdk(monkeypatch, client=None):
    """Monkeypatch all SDK types on the executor module."""
    if client is not None:
        monkeypatch.setattr(f"{SDK_MODULE}.ClaudeSDKClient", lambda *_a, **_kw: client)
    _OptionsRecorder.reset()
    monkeypatch.setattr(f"{SDK_MODULE}.ClaudeAgentOptions", _OptionsRecorder)
    monkeypatch.setattr(f"{SDK_MODULE}.AssistantMessage", _FakeAssistantMessage)
    monkeypatch.setattr(f"{SDK_MODULE}.ResultMessage", _FakeResultMessage)
    monkeypatch.setattr(f"{SDK_MODULE}.TextBlock", _FakeTextBlock)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClaudeA2AExecutor:
    @pytest.mark.asyncio
    async def test_claude_executor_completes_successfully(self, tmp_path, monkeypatch):
        """Mock SDK returns text -> executor completes with artifact."""
        mock_client = _FakeSDKClient(
            messages=[
                _FakeAssistantMessage([_FakeTextBlock("Hello ")]),
                _FakeAssistantMessage([_FakeTextBlock("world")]),
                _FakeResultMessage(result=None, is_error=False),
            ]
        )
        _patch_sdk(monkeypatch, client=mock_client)

        from protocol.a2a.executors.claude_executor import ClaudeA2AExecutor

        executor = ClaudeA2AExecutor(
            model="claude-sonnet-4-5",
            root_dir=str(tmp_path),
        )

        queue = EventQueue()
        context = make_request_context("Say hello")

        await executor.execute(context, queue)

        events = _drain_events(queue)
        await queue.close()

        # Expect: working status, then completed status (+ possible artifact events)
        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        assert len(status_events) >= 2

        # First status: working
        assert status_events[0].status.state == TaskState.working

        # Last status: completed
        last = status_events[-1]
        assert last.status.state == TaskState.completed
        assert last.final is True

        # Verify message text
        msg = last.status.message
        assert msg is not None
        assert len(msg.parts) >= 1
        assert msg.parts[0].root.text == "Hello world"

        # Verify SDK lifecycle
        assert len(mock_client.connect_calls) == 1
        assert mock_client.query_calls == ["Say hello"]
        assert mock_client.disconnect_calls == 1

    @pytest.mark.asyncio
    async def test_claude_executor_handles_error(self, tmp_path, monkeypatch):
        """Mock SDK raises -> executor fails gracefully."""
        mock_client = _FakeSDKClient(connect_error=RuntimeError("connection failed"))
        _patch_sdk(monkeypatch, client=mock_client)

        from protocol.a2a.executors.claude_executor import ClaudeA2AExecutor

        executor = ClaudeA2AExecutor(
            model="claude-sonnet-4-5",
            root_dir=str(tmp_path),
        )

        queue = EventQueue()
        context = make_request_context("Trigger error")

        await executor.execute(context, queue)

        events = _drain_events(queue)
        await queue.close()

        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        assert len(status_events) >= 2

        # First: working, then: failed
        assert status_events[0].status.state == TaskState.working
        last = status_events[-1]
        assert last.status.state == TaskState.failed
        assert last.final is True

        # Error message should be in the parts
        msg = last.status.message
        assert msg is not None
        assert "connection failed" in msg.parts[0].root.text

        # disconnect should still be called (finally block)
        assert mock_client.disconnect_calls == 1

    @pytest.mark.asyncio
    async def test_claude_executor_handles_sdk_error_result(
        self, tmp_path, monkeypatch
    ):
        """SDK returns a ResultMessage with is_error=True -> executor fails."""
        mock_client = _FakeSDKClient(
            messages=[
                _FakeAssistantMessage([_FakeTextBlock("partial output")]),
                _FakeResultMessage(result=None, is_error=True),
            ]
        )
        _patch_sdk(monkeypatch, client=mock_client)

        from protocol.a2a.executors.claude_executor import ClaudeA2AExecutor

        executor = ClaudeA2AExecutor(
            model="claude-sonnet-4-5",
            root_dir=str(tmp_path),
        )

        queue = EventQueue()
        context = make_request_context("Cause SDK error")

        await executor.execute(context, queue)

        events = _drain_events(queue)
        await queue.close()

        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        last = status_events[-1]
        assert last.status.state == TaskState.failed
        assert last.final is True

    @pytest.mark.asyncio
    async def test_claude_executor_cancel(self, tmp_path, monkeypatch):
        """Cancel flow interrupts and disconnects the client."""
        mock_client = _FakeSDKClient()
        _patch_sdk(monkeypatch, client=mock_client)

        from protocol.a2a.executors.claude_executor import ClaudeA2AExecutor

        executor = ClaudeA2AExecutor(
            model="claude-sonnet-4-5",
            root_dir=str(tmp_path),
        )

        # Manually inject a client as if execute() were in progress
        executor._active_clients["test-task-1"] = mock_client  # type: ignore[assignment]

        queue = EventQueue()
        context = make_request_context("cancel me")

        await executor.cancel(context, queue)

        events = _drain_events(queue)
        await queue.close()

        # Should have canceled status
        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        assert len(status_events) == 1
        assert status_events[0].status.state == TaskState.canceled

        # Client should have been interrupted and disconnected
        assert mock_client.interrupt_calls == 1
        assert mock_client.disconnect_calls == 1

        # Client should be removed from active clients
        assert "test-task-1" not in executor._active_clients

    @pytest.mark.asyncio
    async def test_claude_executor_cancel_no_active_client(self, tmp_path, monkeypatch):
        """Cancel when no active client just sends canceled status."""
        _patch_sdk(monkeypatch, client=_FakeSDKClient())

        from protocol.a2a.executors.claude_executor import ClaudeA2AExecutor

        executor = ClaudeA2AExecutor(
            model="claude-sonnet-4-5",
            root_dir=str(tmp_path),
        )

        queue = EventQueue()
        context = make_request_context("cancel nothing")

        await executor.cancel(context, queue)

        events = _drain_events(queue)
        await queue.close()

        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        assert len(status_events) == 1
        assert status_events[0].status.state == TaskState.canceled

    @pytest.mark.asyncio
    async def test_claude_executor_sandbox_callback(self, tmp_path, monkeypatch):
        """Read-only mode applies sandbox callback via _make_sandbox_callback."""
        mock_client = _FakeSDKClient(
            messages=[_FakeResultMessage(result="done", is_error=False)]
        )
        _patch_sdk(monkeypatch, client=mock_client)

        from protocol.a2a.executors.claude_executor import ClaudeA2AExecutor

        executor = ClaudeA2AExecutor(
            model="claude-sonnet-4-5",
            root_dir=str(tmp_path),
            mode="read-only",
        )

        queue = EventQueue()
        context = make_request_context("read only test")

        await executor.execute(context, queue)

        _drain_events(queue)
        await queue.close()

        # Verify ClaudeAgentOptions was called with a can_use_tool callback
        assert _OptionsRecorder.last_call is not None
        assert _OptionsRecorder.last_call.get("can_use_tool") is not None, (
            "read-only mode should pass a sandbox callback"
        )
        assert _OptionsRecorder.last_call.get("permission_mode") == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_claude_executor_readwrite_no_sandbox(self, tmp_path, monkeypatch):
        """Read-write mode passes None for can_use_tool."""
        mock_client = _FakeSDKClient(
            messages=[_FakeResultMessage(result="done", is_error=False)]
        )
        _patch_sdk(monkeypatch, client=mock_client)

        from protocol.a2a.executors.claude_executor import ClaudeA2AExecutor

        executor = ClaudeA2AExecutor(
            model="claude-sonnet-4-5",
            root_dir=str(tmp_path),
            mode="read-write",
        )

        queue = EventQueue()
        context = make_request_context("readwrite test")

        await executor.execute(context, queue)

        _drain_events(queue)
        await queue.close()

        assert _OptionsRecorder.last_call is not None
        assert _OptionsRecorder.last_call.get("can_use_tool") is None, (
            "read-write mode should not apply sandbox callback"
        )
