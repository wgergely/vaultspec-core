"""Unit tests for GeminiA2AExecutor.

Mocks run_subagent() so no Gemini CLI is needed.
Validates the executor correctly maps SubagentResult to A2A events.
"""

from __future__ import annotations

import pytest
from a2a.server.events import EventQueue
from a2a.types import TaskState, TaskStatusUpdateEvent

from protocol.a2a.executors.gemini_executor import GeminiA2AExecutor
from protocol.a2a.tests.conftest import make_request_context
from protocol.acp.types import SubagentResult

_PATCH_TARGET = "protocol.a2a.executors.gemini_executor.run_subagent"


def _drain_events(queue: EventQueue) -> list:
    """Drain all events from queue, calling task_done() for each."""
    events = []
    while not queue.queue.empty():
        events.append(queue.queue.get_nowait())
        queue.task_done()
    return events


class _RunSubagentRecorder:
    """Records calls and returns a preset result from run_subagent."""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls: list[dict] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result

    def assert_awaited_once_with(self, **expected):
        assert len(self.calls) == 1, f"Expected 1 call, got {len(self.calls)}"
        assert self.calls[0] == expected


@pytest.mark.unit
class TestGeminiA2AExecutor:
    @pytest.mark.asyncio
    async def test_gemini_executor_completes_successfully(self, tmp_path, monkeypatch):
        """Mock run_subagent returns response -> executor completes."""
        mock_result = SubagentResult(
            session_id="test-session",
            response_text="Test response from Gemini",
            written_files=[],
        )
        recorder = _RunSubagentRecorder(result=mock_result)
        monkeypatch.setattr(_PATCH_TARGET, recorder)

        executor = GeminiA2AExecutor(
            root_dir=tmp_path,
            model="gemini-2.5-flash",
            agent_name="researcher",
        )
        queue = EventQueue()
        context = make_request_context("Summarize the codebase")

        await executor.execute(context, queue)

        recorder.assert_awaited_once_with(
            agent_name="researcher",
            root_dir=tmp_path,
            initial_task="Summarize the codebase",
            model_override="gemini-2.5-flash",
        )

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
    async def test_gemini_executor_handles_error(self, tmp_path, monkeypatch):
        """Mock run_subagent raises -> executor fails gracefully."""
        recorder = _RunSubagentRecorder(error=RuntimeError("Gemini CLI not found"))
        monkeypatch.setattr(_PATCH_TARGET, recorder)

        executor = GeminiA2AExecutor(
            root_dir=tmp_path,
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
    async def test_gemini_executor_cancel(self, tmp_path):
        """Cancel flow emits canceled status."""
        executor = GeminiA2AExecutor(
            root_dir=tmp_path,
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
    async def test_gemini_executor_empty_response(self, tmp_path, monkeypatch):
        """Empty response_text results in 'Done' fallback message."""
        mock_result = SubagentResult(
            session_id="test-session",
            response_text="",
            written_files=[],
        )
        recorder = _RunSubagentRecorder(result=mock_result)
        monkeypatch.setattr(_PATCH_TARGET, recorder)

        executor = GeminiA2AExecutor(
            root_dir=tmp_path,
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
    async def test_gemini_executor_custom_params(self, tmp_path, monkeypatch):
        """Constructor params are forwarded to run_subagent correctly."""
        mock_result = SubagentResult(
            session_id="s1",
            response_text="OK",
            written_files=[],
        )
        recorder = _RunSubagentRecorder(result=mock_result)

        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()

        monkeypatch.setattr(_PATCH_TARGET, recorder)

        executor = GeminiA2AExecutor(
            root_dir=custom_dir,
            model="gemini-2.0-flash",
            agent_name="writer",
        )
        queue = EventQueue()
        context = make_request_context("Write docs")

        await executor.execute(context, queue)

        recorder.assert_awaited_once_with(
            agent_name="writer",
            root_dir=custom_dir,
            initial_task="Write docs",
            model_override="gemini-2.0-flash",
        )

        events = _drain_events(queue)
        await queue.close()

        assert events[-1].status.state == TaskState.completed
