"""Integration tests for ClaudeA2AExecutor.

Uses constructor DI (client_factory, options_factory) to inject an
in-process SDK client.  Real SDK types (AssistantMessage, ResultMessage,
TextBlock) are used so isinstance checks in the executor work without
any monkeypatching.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from a2a.server.events import EventQueue
from a2a.types import TaskState, TaskStatusUpdateEvent
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
from claude_agent_sdk._errors import MessageParseError

from tests.constants import TEST_PROJECT

from ...providers import ClaudeModels
from ..executors import ClaudeA2AExecutor
from .conftest import make_request_context


def _make_result(
    *,
    result: str | None = None,
    is_error: bool = False,
    session_id: str = "test-session",
) -> ResultMessage:
    """Build a real ResultMessage with sensible defaults for test use."""
    return ResultMessage(
        subtype="result",
        duration_ms=0,
        duration_api_ms=0,
        is_error=is_error,
        num_turns=1,
        session_id=session_id,
        result=result,
    )


async def _async_iter(items: list[Any]):
    """Yield items as an async iterator."""
    for item in items:
        if isinstance(item, Exception):
            raise item
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


class _InProcessSDKClient:
    """In-process implementation of the ClaudeSDKClient interface for DI.

    Injected via ClaudeA2AExecutor's client_factory constructor parameter.
    Yields pre-built real SDK messages (AssistantMessage, ResultMessage)
    so the executor's message-to-event mapping logic is exercised with
    real types.

    disconnect() is callable both sync and async: it returns an awaitable
    so ``await client.disconnect()`` works, but also increments the counter
    when called without await (as the cancel path does).

    Supports multi-round message sequences for retry testing: pass a list
    of lists to ``message_rounds`` — each inner list is yielded by one
    call to ``receive_response()`` / ``receive_messages()``.  If
    ``messages`` is provided instead (the common case), it is treated as
    a single round.
    """

    def __init__(
        self,
        messages=None,
        connect_error=None,
        message_rounds=None,
    ):
        self._message_rounds: list[list[Any]] = (
            message_rounds if message_rounds is not None else [messages or []]
        )
        self._round_idx = 0
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
        return self.receive_response()

    def receive_response(self):
        idx = min(self._round_idx, len(self._message_rounds) - 1)
        self._round_idx += 1
        return _async_iter(self._message_rounds[idx])


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
    client: _InProcessSDKClient,
    model: str = ClaudeModels.MEDIUM,
    mode: str = "read-only",
    root_dir: str | None = None,
    max_retries: int = 3,
    retry_base_delay: float = 0.0,
) -> ClaudeA2AExecutor:
    """Build a ClaudeA2AExecutor with DI'd in-process implementations."""
    _OptionsRecorder.reset()
    return ClaudeA2AExecutor(
        model=model,
        root_dir=root_dir or str(TEST_PROJECT),
        mode=mode,
        client_factory=lambda _opts: client,
        options_factory=_OptionsRecorder,
        max_retries=max_retries,
        retry_base_delay=retry_base_delay,
    )


@pytest.mark.integration
@pytest.mark.claude
class TestClaudeA2AExecutor:
    @pytest.mark.asyncio
    async def test_claude_executor_completes_successfully(self):
        """SDK returns text -> executor completes with artifact."""
        test_client = _InProcessSDKClient(
            messages=[
                AssistantMessage(
                    content=[TextBlock(text="Hello "), TextBlock(text="world")],
                    model=ClaudeModels.MEDIUM,
                ),
                _make_result(result=None, is_error=False),
            ]
        )

        executor = _make_executor(client=test_client)

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
        assert len(test_client.connect_calls) == 1
        assert test_client.query_calls == ["Say hello"]
        assert test_client.disconnect_calls == 1

    @pytest.mark.asyncio
    async def test_claude_executor_handles_error(self):
        """SDK raises -> executor fails gracefully."""
        test_client = _InProcessSDKClient(
            connect_error=RuntimeError("connection failed")
        )

        executor = _make_executor(client=test_client)

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
        assert test_client.disconnect_calls == 1

    @pytest.mark.asyncio
    async def test_claude_executor_handles_sdk_error_result(self):
        """SDK returns a ResultMessage with is_error=True -> executor fails."""
        test_client = _InProcessSDKClient(
            messages=[
                AssistantMessage(
                    content=[TextBlock(text="partial output")],
                    model=ClaudeModels.MEDIUM,
                ),
                _make_result(result=None, is_error=True),
            ]
        )

        executor = _make_executor(client=test_client)

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
        """Cancel flow interrupts client but does NOT disconnect or remove it."""
        test_client = _InProcessSDKClient()

        executor = _make_executor(client=test_client)

        # Manually inject a client as if execute() were in progress
        executor._active_clients["test-task-1"] = test_client
        executor._cancel_events["test-task-1"] = asyncio.Event()

        queue = EventQueue()
        context = make_request_context("cancel me")

        await executor.cancel(context, queue)

        events = _drain_events(queue)
        await queue.close()

        # Should have canceled status
        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        assert len(status_events) == 1
        assert status_events[0].status.state == TaskState.canceled

        # Client should have been interrupted but NOT disconnected
        assert test_client.interrupt_calls == 1
        assert test_client.disconnect_calls == 0

        # Client should still be in active clients
        assert "test-task-1" in executor._active_clients

    @pytest.mark.asyncio
    async def test_claude_executor_cancel_no_active_client(self):
        """Cancel when no active client just sends canceled status."""
        test_client = _InProcessSDKClient()

        executor = _make_executor(client=test_client)

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
        test_client = _InProcessSDKClient(
            messages=[_make_result(result="done", is_error=False)]
        )

        executor = _make_executor(client=test_client, mode="read-only")

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
        test_client = _InProcessSDKClient(
            messages=[_make_result(result="done", is_error=False)]
        )

        executor = _make_executor(client=test_client, mode="read-write")

        queue = EventQueue()
        context = make_request_context("readwrite test")

        await executor.execute(context, queue)

        _drain_events(queue)
        await queue.close()

        assert _OptionsRecorder.last_call is not None
        assert _OptionsRecorder.last_call.get("can_use_tool") is None, (
            "read-write mode should not apply sandbox callback"
        )

    # ------------------------------------------------------------------
    # New tests: retry, session resume, cancel semantics, progress
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self):
        """MessageParseError with rate_limit triggers retry, then succeeds."""
        test_client = _InProcessSDKClient(
            message_rounds=[
                # Round 1: rate-limit parse error kills the stream
                [MessageParseError("Unknown message type: rate_limit_event")],
                # Round 2: normal completion
                [
                    AssistantMessage(
                        content=[TextBlock(text="recovered")],
                        model=ClaudeModels.MEDIUM,
                    ),
                    _make_result(result=None, is_error=False),
                ],
            ]
        )

        executor = _make_executor(
            client=test_client, max_retries=3, retry_base_delay=0.0
        )

        queue = EventQueue()
        context = make_request_context("rate limit me")

        await executor.execute(context, queue)

        events = _drain_events(queue)
        await queue.close()

        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        last = status_events[-1]
        assert last.status.state == TaskState.completed
        assert last.final is True

        # Should have queried twice (initial + retry)
        assert len(test_client.query_calls) == 2

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        """Repeated rate-limit errors exhaust max_retries -> task fails."""
        # 4 rounds of rate-limit errors (1 initial + 3 retries = 4 total
        # attempts, but max_retries=2 means only 2 retry attempts allowed)
        test_client = _InProcessSDKClient(
            message_rounds=[
                [MessageParseError("rate_limit_event")],
                [MessageParseError("rate_limit_event")],
                [MessageParseError("rate_limit_event")],
                [MessageParseError("rate_limit_event")],
            ]
        )

        executor = _make_executor(
            client=test_client, max_retries=2, retry_base_delay=0.0
        )

        queue = EventQueue()
        context = make_request_context("exhaust retries")

        await executor.execute(context, queue)

        events = _drain_events(queue)
        await queue.close()

        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        last = status_events[-1]
        assert last.status.state == TaskState.failed
        assert last.final is True
        assert "retries" in last.status.message.parts[0].root.text.lower()

    @pytest.mark.asyncio
    async def test_session_resume(self):
        """Second execution with same context_id includes resume in options."""
        test_client = _InProcessSDKClient(
            message_rounds=[
                # First call: result with session_id
                [_make_result(result="first", is_error=False, session_id="sess-42")],
                # Second call: result
                [_make_result(result="second", is_error=False, session_id="sess-43")],
            ]
        )

        executor = _make_executor(client=test_client)

        # First execution — no resume expected
        queue1 = EventQueue()
        ctx1 = make_request_context(
            "first call", task_id="task-A", context_id="ctx-shared"
        )
        await executor.execute(ctx1, queue1)
        _drain_events(queue1)
        await queue1.close()

        first_opts = _OptionsRecorder.last_call
        assert first_opts is not None
        assert "resume" not in first_opts, "First call should not have resume"

        # Second execution — same context_id, should resume
        queue2 = EventQueue()
        ctx2 = make_request_context(
            "second call", task_id="task-B", context_id="ctx-shared"
        )
        await executor.execute(ctx2, queue2)
        _drain_events(queue2)
        await queue2.close()

        second_opts = _OptionsRecorder.last_call
        assert second_opts is not None
        assert second_opts.get("resume") == "sess-42"

    @pytest.mark.asyncio
    async def test_cancel_non_destructive(self):
        """Cancel interrupts the client but does not disconnect or remove it."""
        test_client = _InProcessSDKClient()

        executor = _make_executor(client=test_client)

        # Simulate an in-progress execution
        executor._active_clients["test-task-1"] = test_client
        executor._cancel_events["test-task-1"] = asyncio.Event()

        queue = EventQueue()
        context = make_request_context("cancel me")

        await executor.cancel(context, queue)

        _drain_events(queue)
        await queue.close()

        assert test_client.interrupt_calls == 1
        assert test_client.disconnect_calls == 0
        assert "test-task-1" in executor._active_clients

    @pytest.mark.asyncio
    async def test_streaming_progress_events(self):
        """Intermediate status updates are emitted between working and completed."""
        test_client = _InProcessSDKClient(
            messages=[
                AssistantMessage(
                    content=[TextBlock(text="chunk-1")],
                    model=ClaudeModels.MEDIUM,
                ),
                AssistantMessage(
                    content=[TextBlock(text=" chunk-2")],
                    model=ClaudeModels.MEDIUM,
                ),
                _make_result(result=None, is_error=False),
            ]
        )

        executor = _make_executor(client=test_client)

        queue = EventQueue()
        context = make_request_context("stream progress")

        await executor.execute(context, queue)

        events = _drain_events(queue)
        await queue.close()

        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]

        # At minimum: working, then at least one progress update, then completed
        assert len(status_events) >= 3
        assert status_events[0].status.state == TaskState.working

        # All intermediate statuses should be 'working'
        for se in status_events[1:-1]:
            assert se.status.state == TaskState.working

        assert status_events[-1].status.state == TaskState.completed
        assert status_events[-1].final is True

    @pytest.mark.asyncio
    async def test_assistant_message_error(self):
        """AssistantMessage with error='rate_limit' triggers retry."""
        test_client = _InProcessSDKClient(
            message_rounds=[
                # Round 1: rate_limit error on AssistantMessage
                [
                    AssistantMessage(
                        content=[],
                        model=ClaudeModels.MEDIUM,
                        error="rate_limit",
                    ),
                ],
                # Round 2: normal completion
                [
                    AssistantMessage(
                        content=[TextBlock(text="ok")],
                        model=ClaudeModels.MEDIUM,
                    ),
                    _make_result(result=None, is_error=False),
                ],
            ]
        )

        executor = _make_executor(
            client=test_client, max_retries=3, retry_base_delay=0.0
        )

        queue = EventQueue()
        context = make_request_context("rate limit via error field")

        await executor.execute(context, queue)

        events = _drain_events(queue)
        await queue.close()

        status_events = [e for e in events if isinstance(e, TaskStatusUpdateEvent)]
        last = status_events[-1]
        assert last.status.state == TaskState.completed
        assert last.final is True

        # Two query calls: initial + one retry
        assert len(test_client.query_calls) == 2
