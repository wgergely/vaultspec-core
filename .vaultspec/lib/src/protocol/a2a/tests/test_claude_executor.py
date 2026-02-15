"""Unit tests for ClaudeA2AExecutor.

Uses constructor DI (client_factory, options_factory) so no SDK patching is
needed.  Fake SDK client controls the message stream; real SDK types are used
for AssistantMessage, ResultMessage, and TextBlock so isinstance checks in
the executor work without any monkeypatching.
"""

from __future__ import annotations

from typing import Any

import pytest
from a2a.server.events import EventQueue
from a2a.types import TaskState, TaskStatusUpdateEvent
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from protocol.a2a.executors.claude_executor import ClaudeA2AExecutor
from protocol.a2a.tests.conftest import TEST_PROJECT, make_request_context

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    *,
    result: str | None = None,
    is_error: bool = False,
) -> ResultMessage:
    """Build a real ResultMessage with sensible defaults for test use."""
    return ResultMessage(
        subtype="result",
        duration_ms=0,
        duration_api_ms=0,
        is_error=is_error,
        num_turns=1,
        session_id="test-session",
        result=result,
    )


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
    """Records kwargs passed to the options factory."""

    last_call: dict | None = None

    def __init__(self, **kwargs):
        _OptionsRecorder.last_call = kwargs

    @classmethod
    def reset(cls):
        cls.last_call = None


def _make_executor(
    *,
    client: _FakeSDKClient,
    model: str = "claude-sonnet-4-5",
    mode: str = "read-only",
    root_dir: str | None = None,
) -> ClaudeA2AExecutor:
    """Build a ClaudeA2AExecutor with DI'd fakes."""
    _OptionsRecorder.reset()
    return ClaudeA2AExecutor(
        model=model,
        root_dir=root_dir or str(TEST_PROJECT),
        mode=mode,
        client_factory=lambda _opts: client,
        options_factory=_OptionsRecorder,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClaudeA2AExecutor:
    @pytest.mark.asyncio
    async def test_claude_executor_completes_successfully(self):
        """SDK returns text -> executor completes with artifact."""
        fake_client = _FakeSDKClient(
            messages=[
                AssistantMessage(
                    content=[TextBlock(text="Hello "), TextBlock(text="world")],
                    model="claude-sonnet-4-5",
                ),
                _make_result(result=None, is_error=False),
            ]
        )

        executor = _make_executor(client=fake_client)

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
        assert len(fake_client.connect_calls) == 1
        assert fake_client.query_calls == ["Say hello"]
        assert fake_client.disconnect_calls == 1

    @pytest.mark.asyncio
    async def test_claude_executor_handles_error(self):
        """SDK raises -> executor fails gracefully."""
        fake_client = _FakeSDKClient(connect_error=RuntimeError("connection failed"))

        executor = _make_executor(client=fake_client)

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
        assert fake_client.disconnect_calls == 1

    @pytest.mark.asyncio
    async def test_claude_executor_handles_sdk_error_result(self):
        """SDK returns a ResultMessage with is_error=True -> executor fails."""
        fake_client = _FakeSDKClient(
            messages=[
                AssistantMessage(
                    content=[TextBlock(text="partial output")],
                    model="claude-sonnet-4-5",
                ),
                _make_result(result=None, is_error=True),
            ]
        )

        executor = _make_executor(client=fake_client)

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
    async def test_claude_executor_cancel(self):
        """Cancel flow interrupts and disconnects the client."""
        fake_client = _FakeSDKClient()

        executor = _make_executor(client=fake_client)

        # Manually inject a client as if execute() were in progress
        executor._active_clients["test-task-1"] = fake_client

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
        assert fake_client.interrupt_calls == 1
        assert fake_client.disconnect_calls == 1

        # Client should be removed from active clients
        assert "test-task-1" not in executor._active_clients

    @pytest.mark.asyncio
    async def test_claude_executor_cancel_no_active_client(self):
        """Cancel when no active client just sends canceled status."""
        fake_client = _FakeSDKClient()

        executor = _make_executor(client=fake_client)

        queue = EventQueue()
        context = make_request_context("cancel nothing")

        await executor.cancel(context, queue)

        events = _drain_events(queue)
        await queue.close()

        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        assert len(status_events) == 1
        assert status_events[0].status.state == TaskState.canceled

    @pytest.mark.asyncio
    async def test_claude_executor_sandbox_callback(self):
        """Read-only mode applies sandbox callback via _make_sandbox_callback."""
        fake_client = _FakeSDKClient(
            messages=[_make_result(result="done", is_error=False)]
        )

        executor = _make_executor(client=fake_client, mode="read-only")

        queue = EventQueue()
        context = make_request_context("read only test")

        await executor.execute(context, queue)

        _drain_events(queue)
        await queue.close()

        # Verify options factory was called with a can_use_tool callback
        assert _OptionsRecorder.last_call is not None
        assert _OptionsRecorder.last_call.get("can_use_tool") is not None, (
            "read-only mode should pass a sandbox callback"
        )
        assert _OptionsRecorder.last_call.get("permission_mode") == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_claude_executor_readwrite_no_sandbox(self):
        """Read-write mode passes None for can_use_tool."""
        fake_client = _FakeSDKClient(
            messages=[_make_result(result="done", is_error=False)]
        )

        executor = _make_executor(client=fake_client, mode="read-write")

        queue = EventQueue()
        context = make_request_context("readwrite test")

        await executor.execute(context, queue)

        _drain_events(queue)
        await queue.close()

        assert _OptionsRecorder.last_call is not None
        assert _OptionsRecorder.last_call.get("can_use_tool") is None, (
            "read-write mode should not apply sandbox callback"
        )
