"""Unit tests for GeminiA2AExecutor.

Injects a test run_subagent via constructor DI so no Gemini CLI is needed.
Validates the executor correctly maps SubagentResult to A2A events.
"""

from __future__ import annotations

import asyncio

import pytest
from a2a.server.events import EventQueue
from a2a.types import TaskState, TaskStatusUpdateEvent

from tests.constants import TEST_PROJECT

from ...acp import SubagentResult
from ...providers import GeminiModels
from ..executors import GeminiA2AExecutor
from .conftest import make_request_context


def _drain_events(queue: EventQueue) -> list:
    """Drain all events from queue, calling task_done() for each."""
    events = []
    while not queue.queue.empty():
        events.append(queue.queue.get_nowait())
        queue.task_done()
    return events


class _RunSubagentRecorder:
    """Records calls and returns a preset result from run_subagent."""

    def __init__(self, result=None, error=None, delay: float = 0):
        self.result = result
        self.error = error
        self.delay = delay
        self.calls: list[dict] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.result


class _FailThenSucceedRecorder:
    """Fails ``fail_count`` times with ``error``, then returns ``result``."""

    def __init__(self, *, result, error, fail_count):
        self.result = result
        self.error = error
        self.fail_count = fail_count
        self.calls: list[dict] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) <= self.fail_count:
            raise self.error
        return self.result


@pytest.mark.unit
class TestGeminiA2AExecutor:
    @pytest.mark.asyncio
    async def test_gemini_executor_completes_successfully(self):
        """Injected run_subagent returns response -> executor completes."""
        expected_result = SubagentResult(
            session_id="test-session",
            response_text="Test response from Gemini",
            written_files=[],
        )
        recorder = _RunSubagentRecorder(result=expected_result)

        executor = GeminiA2AExecutor(
            root_dir=TEST_PROJECT,
            model=GeminiModels.LOW,
            agent_name="vaultspec-researcher",
            run_subagent=recorder,
        )
        queue = EventQueue()
        context = make_request_context("Summarize the codebase")

        await executor.execute(context, queue)

        assert len(recorder.calls) == 1
        assert recorder.calls[0] == {
            "agent_name": "vaultspec-researcher",
            "root_dir": TEST_PROJECT,
            "initial_task": "Summarize the codebase",
            "model_override": GeminiModels.LOW,
            "resume_session_id": None,
        }

        events = _drain_events(queue)
        await queue.close()

        # Expect: working, artifact, completed
        assert len(events) == 3
        assert isinstance(events[0], TaskStatusUpdateEvent)
        assert events[0].status.state == TaskState.working

        # Final event is completed
        assert isinstance(events[-1], TaskStatusUpdateEvent)
        assert events[-1].status.state == TaskState.completed
        assert events[-1].final is True

        msg = events[-1].status.message
        assert msg is not None
        assert msg.parts[0].root.text == "Test response from Gemini"

    @pytest.mark.asyncio
    async def test_gemini_executor_handles_error(self):
        """Injected run_subagent raises -> executor fails gracefully."""
        recorder = _RunSubagentRecorder(error=RuntimeError("Gemini CLI not found"))

        executor = GeminiA2AExecutor(
            root_dir=TEST_PROJECT,
            run_subagent=recorder,
        )
        queue = EventQueue()
        context = make_request_context("Do something")

        await executor.execute(context, queue)

        events = _drain_events(queue)
        await queue.close()

        # Expect: working, then failed
        assert len(events) == 2
        assert events[0].status.state == TaskState.working
        assert events[1].status.state == TaskState.failed
        assert events[1].final is True

        msg = events[1].status.message
        assert msg is not None
        assert "Gemini CLI not found" in msg.parts[0].root.text

    @pytest.mark.asyncio
    async def test_gemini_executor_cancel(self):
        """Cancel flow emits canceled status."""
        executor = GeminiA2AExecutor(
            root_dir=TEST_PROJECT,
            run_subagent=_RunSubagentRecorder(),
        )
        queue = EventQueue()
        context = make_request_context("Cancel me")

        await executor.cancel(context, queue)

        events = _drain_events(queue)
        await queue.close()

        assert len(events) == 1
        assert events[0].status.state == TaskState.canceled
        assert events[0].final is True

    @pytest.mark.asyncio
    async def test_gemini_executor_empty_response(self):
        """Empty response_text results in 'Done' fallback message."""
        expected_result = SubagentResult(
            session_id="test-session",
            response_text="",
            written_files=[],
        )
        recorder = _RunSubagentRecorder(result=expected_result)

        executor = GeminiA2AExecutor(
            root_dir=TEST_PROJECT,
            run_subagent=recorder,
        )
        queue = EventQueue()
        context = make_request_context("Empty task")

        await executor.execute(context, queue)

        events = _drain_events(queue)
        await queue.close()

        # Empty response -> no artifact, just working + completed
        assert len(events) == 2
        assert events[0].status.state == TaskState.working
        assert events[1].status.state == TaskState.completed
        assert events[1].final is True

        # Fallback text is "Done"
        msg = events[1].status.message
        assert msg is not None
        assert msg.parts[0].root.text == "Done"

    @pytest.mark.asyncio
    async def test_gemini_executor_custom_params(self):
        """Constructor params are forwarded to run_subagent correctly."""
        expected_result = SubagentResult(
            session_id="s1",
            response_text="OK",
            written_files=[],
        )
        recorder = _RunSubagentRecorder(result=expected_result)

        custom_dir = TEST_PROJECT / "custom"

        executor = GeminiA2AExecutor(
            root_dir=custom_dir,
            model=GeminiModels.MEDIUM,
            agent_name="writer",
            run_subagent=recorder,
        )
        queue = EventQueue()
        context = make_request_context("Write docs")

        await executor.execute(context, queue)

        assert len(recorder.calls) == 1
        assert recorder.calls[0] == {
            "agent_name": "writer",
            "root_dir": custom_dir,
            "initial_task": "Write docs",
            "model_override": GeminiModels.MEDIUM,
            "resume_session_id": None,
        }

        events = _drain_events(queue)
        await queue.close()

        assert events[-1].status.state == TaskState.completed


@pytest.mark.unit
class TestGeminiA2AExecutorRetry:
    """Tests for bounded retry with exponential backoff (Decision 5a)."""

    @pytest.mark.asyncio
    async def test_retry_on_transient_error_then_success(self):
        """Transient errors trigger retry; eventual success completes the task."""
        expected = SubagentResult(
            session_id="s-retry",
            response_text="Recovered",
            written_files=[],
        )
        recorder = _FailThenSucceedRecorder(
            result=expected,
            error=ConnectionError("connection reset"),
            fail_count=2,
        )

        executor = GeminiA2AExecutor(
            root_dir=TEST_PROJECT,
            run_subagent=recorder,
            max_retries=3,
            retry_base_delay=0.01,
        )
        queue = EventQueue()
        context = make_request_context("Retry me")

        await executor.execute(context, queue)

        # 2 failures + 1 success = 3 calls.
        assert len(recorder.calls) == 3

        events = _drain_events(queue)
        await queue.close()

        assert events[-1].status.state == TaskState.completed
        assert events[-1].final is True
        assert events[-1].status.message.parts[0].root.text == "Recovered"

        # Should have retry status updates in the event stream.
        working_events = [
            e
            for e in events
            if isinstance(e, TaskStatusUpdateEvent)
            and e.status.state == TaskState.working
        ]
        # At least: initial start_work + 2 retry updates.
        assert len(working_events) >= 3

    @pytest.mark.asyncio
    async def test_retry_exhaustion_fails(self):
        """Exhausting max_retries on retryable errors fails the task."""
        recorder = _RunSubagentRecorder(
            error=ConnectionError("connection refused"),
        )

        executor = GeminiA2AExecutor(
            root_dir=TEST_PROJECT,
            run_subagent=recorder,
            max_retries=2,
            retry_base_delay=0.01,
        )
        queue = EventQueue()
        context = make_request_context("Fail forever")

        await executor.execute(context, queue)

        # 1 initial + 2 retries = 3 calls.
        assert len(recorder.calls) == 3

        events = _drain_events(queue)
        await queue.close()

        assert events[-1].status.state == TaskState.failed
        assert events[-1].final is True

    @pytest.mark.asyncio
    async def test_non_retryable_error_fails_immediately(self):
        """Non-retryable errors (e.g., missing executable) fail without retry."""
        recorder = _RunSubagentRecorder(
            error=FileNotFoundError("gemini: command not found"),
        )

        executor = GeminiA2AExecutor(
            root_dir=TEST_PROJECT,
            run_subagent=recorder,
            max_retries=3,
            retry_base_delay=0.01,
        )
        queue = EventQueue()
        context = make_request_context("Missing exe")

        await executor.execute(context, queue)

        # Only 1 call — no retries.
        assert len(recorder.calls) == 1

        events = _drain_events(queue)
        await queue.close()

        assert events[-1].status.state == TaskState.failed
        assert events[-1].final is True
        error_text = events[-1].status.message.parts[0].root.text
        assert "gemini: command not found" in error_text

    @pytest.mark.asyncio
    async def test_rate_limit_string_triggers_retry(self):
        """Exception message containing 'rate_limit' is classified as retryable."""
        expected = SubagentResult(
            session_id=None,
            response_text="OK after rate limit",
            written_files=[],
        )
        recorder = _FailThenSucceedRecorder(
            result=expected,
            error=RuntimeError("rate_limit: 429 Too Many Requests"),
            fail_count=1,
        )

        executor = GeminiA2AExecutor(
            root_dir=TEST_PROJECT,
            run_subagent=recorder,
            max_retries=3,
            retry_base_delay=0.01,
        )
        queue = EventQueue()
        context = make_request_context("Rate limited")

        await executor.execute(context, queue)

        assert len(recorder.calls) == 2
        events = _drain_events(queue)
        await queue.close()

        assert events[-1].status.state == TaskState.completed


@pytest.mark.unit
class TestGeminiA2AExecutorCancel:
    """Tests for non-destructive cancel (Decision 5c)."""

    @pytest.mark.asyncio
    async def test_cancel_during_execute(self):
        """Cancelling a running task terminates the subagent and emits canceled."""
        recorder = _RunSubagentRecorder(
            result=SubagentResult(response_text="late", written_files=[]),
            delay=10.0,
        )

        executor = GeminiA2AExecutor(
            root_dir=TEST_PROJECT,
            run_subagent=recorder,
        )
        queue = EventQueue()
        context = make_request_context("Long task", task_id="cancel-task-1")

        exec_task = asyncio.create_task(executor.execute(context, queue))
        await asyncio.sleep(0.05)

        cancel_queue = EventQueue()
        cancel_ctx = make_request_context(
            "cancel", task_id="cancel-task-1", context_id="test-ctx-1"
        )
        await executor.cancel(cancel_ctx, cancel_queue)
        await asyncio.wait_for(exec_task, timeout=2.0)

        exec_events = _drain_events(queue)
        await queue.close()
        cancel_events = _drain_events(cancel_queue)
        await cancel_queue.close()

        # cancel() emits its own canceled event.
        assert any(
            isinstance(e, TaskStatusUpdateEvent)
            and e.status.state == TaskState.canceled
            for e in cancel_events
        )

        # execute() should also have terminated.
        terminal_states = [
            e.status.state
            for e in exec_events
            if isinstance(e, TaskStatusUpdateEvent) and e.final
        ]
        assert terminal_states, "Expected at least one terminal event from execute()"
        assert terminal_states[-1] == TaskState.canceled


@pytest.mark.unit
class TestGeminiA2AExecutorHeartbeat:
    """Tests for heartbeat progress events (Decision 5b)."""

    @pytest.mark.asyncio
    async def test_heartbeat_emits_working_events(self):
        """Heartbeat emits periodic working updates during long subagent runs."""
        recorder = _RunSubagentRecorder(
            result=SubagentResult(
                response_text="Finally done",
                written_files=[],
            ),
            delay=0.15,
        )

        executor = GeminiA2AExecutor(
            root_dir=TEST_PROJECT,
            run_subagent=recorder,
            _heartbeat_interval=0.05,
        )
        queue = EventQueue()
        context = make_request_context("Slow task")

        await executor.execute(context, queue)

        events = _drain_events(queue)
        await queue.close()

        working_events = [
            e
            for e in events
            if isinstance(e, TaskStatusUpdateEvent)
            and e.status.state == TaskState.working
        ]
        # At least the initial start_work + 1 heartbeat.
        assert len(working_events) >= 2

        assert events[-1].status.state == TaskState.completed


@pytest.mark.unit
class TestGeminiA2AExecutorConcurrency:
    """Tests for concurrency protection (Decision 5d)."""

    @pytest.mark.asyncio
    async def test_concurrent_execution(self):
        """Two concurrent execute() calls on the same executor both complete."""
        result_a = SubagentResult(response_text="Result A", written_files=[])
        result_b = SubagentResult(response_text="Result B", written_files=[])

        call_count = 0

        async def _alternating_subagent(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(0.02)
                return result_a
            return result_b

        executor = GeminiA2AExecutor(
            root_dir=TEST_PROJECT,
            run_subagent=_alternating_subagent,
        )

        queue_a = EventQueue()
        queue_b = EventQueue()
        ctx_a = make_request_context("Task A", task_id="t-a", context_id="c-a")
        ctx_b = make_request_context("Task B", task_id="t-b", context_id="c-b")

        await asyncio.gather(
            executor.execute(ctx_a, queue_a),
            executor.execute(ctx_b, queue_b),
        )

        events_a = _drain_events(queue_a)
        events_b = _drain_events(queue_b)
        await queue_a.close()
        await queue_b.close()

        assert events_a[-1].status.state == TaskState.completed
        assert events_b[-1].status.state == TaskState.completed


@pytest.mark.unit
class TestGeminiA2AExecutorSessionResume:
    """Tests for session resume infrastructure (Decision 5e)."""

    @pytest.mark.asyncio
    async def test_session_id_stored_by_context(self):
        """Successful execution stores session_id keyed by context_id."""
        expected = SubagentResult(
            session_id="gemini-sess-42",
            response_text="Done",
            written_files=[],
        )
        recorder = _RunSubagentRecorder(result=expected)

        executor = GeminiA2AExecutor(
            root_dir=TEST_PROJECT,
            run_subagent=recorder,
        )
        queue = EventQueue()
        context = make_request_context(
            "Store session",
            task_id="t-sess",
            context_id="ctx-sess-1",
        )

        await executor.execute(context, queue)

        _drain_events(queue)
        await queue.close()

        assert executor._session_ids.get("ctx-sess-1") == "gemini-sess-42"

    @pytest.mark.asyncio
    async def test_none_session_id_not_stored(self):
        """None session_id is not stored in the session map."""
        expected = SubagentResult(
            session_id=None,
            response_text="No session",
            written_files=[],
        )
        recorder = _RunSubagentRecorder(result=expected)

        executor = GeminiA2AExecutor(
            root_dir=TEST_PROJECT,
            run_subagent=recorder,
        )
        queue = EventQueue()
        context = make_request_context(
            "No session",
            task_id="t-no-sess",
            context_id="ctx-no-sess",
        )

        await executor.execute(context, queue)

        _drain_events(queue)
        await queue.close()

        assert "ctx-no-sess" not in executor._session_ids

    @pytest.mark.asyncio
    async def test_none_response_text(self):
        """None response_text is treated as empty and falls back to 'Done'."""
        expected = SubagentResult(
            session_id=None,
            response_text=None,  # type: ignore[arg-type]
            written_files=[],
        )
        recorder = _RunSubagentRecorder(result=expected)

        executor = GeminiA2AExecutor(
            root_dir=TEST_PROJECT,
            run_subagent=recorder,
        )
        queue = EventQueue()
        context = make_request_context("None response")

        await executor.execute(context, queue)

        events = _drain_events(queue)
        await queue.close()

        assert len(events) == 2
        assert events[0].status.state == TaskState.working
        assert events[1].status.state == TaskState.completed
        assert events[1].status.message.parts[0].root.text == "Done"
