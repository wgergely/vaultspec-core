"""A2A AgentExecutor wrapping Gemini via existing ACP subprocess.

Uses run_subagent() to delegate to GeminiProvider's ACP flow,
mapping results back to A2A events.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import subprocess
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TaskState, TextPart

from ....orchestration import run_subagent as _default_run_subagent
from ...providers import GeminiModels

if TYPE_CHECKING:
    import pathlib

    from a2a.server.events import EventQueue

logger = logging.getLogger(__name__)

__all__ = ["GeminiA2AExecutor"]

# Default interval between heartbeat progress updates.
_HEARTBEAT_INTERVAL_SECS = 5.0

# Exception types that indicate a transient, retryable failure.
_RETRYABLE_EXCEPTIONS = (
    subprocess.TimeoutExpired,
    ConnectionError,
    OSError,
)

# Strings in exception messages that indicate retryable failures.
_RETRYABLE_PATTERNS = ("rate_limit", "timeout", "connection")


def _is_retryable(exc: Exception) -> bool:
    """Return True if the exception indicates a transient, retryable failure.

    ``FileNotFoundError`` is excluded even though it is an ``OSError``
    subclass because a missing executable is a permanent failure.

    Args:
        exc: The exception to classify.

    Returns:
        True if the failure is transient and the caller should retry.
    """
    # FileNotFoundError is an OSError subclass but indicates a permanent failure
    # (missing executable).
    if isinstance(exc, (FileNotFoundError, ValueError, TypeError)):
        return False
    if isinstance(exc, _RETRYABLE_EXCEPTIONS):
        return True
    msg = str(exc).lower()
    return any(pattern in msg for pattern in _RETRYABLE_PATTERNS)


class GeminiA2AExecutor(AgentExecutor):
    """A2A executor that delegates to Gemini via the existing ACP subprocess flow.

    Wraps ``run_subagent()`` from ``orchestration.subagent``, mapping the
    ``SubagentResult`` back to A2A task lifecycle events.

    Parameters
    ----------
    root_dir:
        Workspace root for the agent subprocess.
    model:
        Gemini model identifier.
    agent_name:
        Name of the agent definition to load.
    run_subagent:
        Callable to spawn the subagent.  Defaults to the real
        ``orchestration.subagent.run_subagent``.  Override in tests to
        inject a test implementation via constructor DI.
    max_retries:
        Maximum number of retries on transient errors before failing.
    retry_base_delay:
        Base delay in seconds for exponential back-off between retries.
    """

    def __init__(
        self,
        *,
        root_dir: pathlib.Path,
        model: str = GeminiModels.LOW,
        agent_name: str = "vaultspec-researcher",
        run_subagent: Callable[..., Any] | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        _heartbeat_interval: float = _HEARTBEAT_INTERVAL_SECS,
    ) -> None:
        """Initialise the executor with subagent configuration.

        Args:
            root_dir: Workspace root for the agent subprocess.
            model: Gemini model identifier (e.g. ``GeminiModels.LOW``).
            agent_name: Name of the agent definition to load.
            run_subagent: Callable to spawn the subagent.  Defaults to
                ``orchestration.subagent.run_subagent``.
            max_retries: Maximum retries on transient errors before failing.
            retry_base_delay: Base delay in seconds for exponential back-off.
            _heartbeat_interval: Interval in seconds between heartbeat progress
                updates emitted while the subagent task is blocking.
        """
        self._root_dir = root_dir
        self._model = model
        self._agent_name = agent_name
        self._run_subagent = run_subagent or _default_run_subagent
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._heartbeat_interval = _heartbeat_interval
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._tasks_lock = asyncio.Lock()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute an A2A task by delegating to the Gemini subagent.

        Runs ``run_subagent()`` as an async task and emits periodic heartbeat
        progress updates while it blocks.  Implements exponential back-off
        retry for transient errors.

        Args:
            context: The A2A request context carrying the task ID, context ID,
                and user input prompt.
            event_queue: The A2A event queue used to emit status updates,
                artifacts, and terminal events.
        """
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        updater = TaskUpdater(event_queue, task_id, context_id)
        prompt = context.get_user_input()

        logger.info(
            "GeminiA2AExecutor starting task %s with agent %s",
            task_id,
            self._agent_name,
        )

        await updater.start_work()

        cancel_event = asyncio.Event()
        async with self._tasks_lock:
            self._cancel_events[task_id] = cancel_event

        try:
            attempt = 0
            while True:
                if cancel_event.is_set():
                    with contextlib.suppress(RuntimeError):
                        await updater.cancel()
                    return

                logger.debug(
                    "Running subagent for task %s (attempt %d)", task_id, attempt
                )

                subagent_task = asyncio.create_task(
                    self._run_subagent(
                        agent_name=self._agent_name,
                        root_dir=self._root_dir,
                        initial_task=prompt,
                        model_override=self._model,
                    )
                )
                async with self._tasks_lock:
                    self._running_tasks[task_id] = subagent_task

                heartbeat_task = asyncio.create_task(
                    self._heartbeat(updater, cancel_event)
                )

                try:
                    result = await subagent_task
                except asyncio.CancelledError:
                    with contextlib.suppress(RuntimeError):
                        await updater.cancel()
                    return
                except Exception as exc:
                    if not _is_retryable(exc) or attempt >= self._max_retries:
                        logger.error(
                            "GeminiA2AExecutor error for task %s (attempt %d/%d)",
                            task_id,
                            attempt,
                            self._max_retries,
                            exc_info=True,
                        )
                        await updater.failed(
                            message=updater.new_agent_message(
                                parts=[Part(root=TextPart(text=str(exc)))]
                            )
                        )
                        return

                    attempt += 1
                    delay = self._retry_base_delay * (2**attempt)
                    await updater.update_status(
                        TaskState.working,
                        message=updater.new_agent_message(
                            parts=[
                                Part(
                                    root=TextPart(
                                        text=(
                                            f"Transient error, retrying "
                                            f"(attempt {attempt}"
                                            f"/{self._max_retries})"
                                        )
                                    )
                                )
                            ]
                        ),
                    )
                    logger.info(
                        "Retryable error on task %s, retrying in %.1fs "
                        "(attempt %d/%d): %s",
                        task_id,
                        delay,
                        attempt,
                        self._max_retries,
                        exc,
                    )
                    # Sleep with cancel awareness: if the cancel event fires
                    # during backoff, respond immediately instead of waiting.
                    try:
                        await asyncio.wait_for(cancel_event.wait(), timeout=delay)
                        with contextlib.suppress(RuntimeError):
                            await updater.cancel()
                        return
                    except TimeoutError:
                        pass
                    continue
                finally:
                    heartbeat_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await heartbeat_task
                    async with self._tasks_lock:
                        self._running_tasks.pop(task_id, None)

                # Success path.
                text = result.response_text or ""
                if text:
                    logger.debug("Got response for task %s, adding artifact", task_id)
                    await updater.add_artifact(
                        parts=[Part(root=TextPart(text=text))],
                        name="response",
                    )
                logger.info("Task %s completed successfully", task_id)
                await updater.complete(
                    message=updater.new_agent_message(
                        parts=[Part(root=TextPart(text=text or "Done"))]
                    )
                )
                return

        finally:
            async with self._tasks_lock:
                self._cancel_events.pop(task_id, None)
                self._running_tasks.pop(task_id, None)

    async def _heartbeat(
        self, updater: TaskUpdater, cancel_event: asyncio.Event
    ) -> None:
        """Emit periodic ``TaskState.working`` updates while run_subagent blocks.

        Args:
            updater: Task updater used to push working-state status events.
            cancel_event: Asyncio event; when set the heartbeat loop exits.
        """
        while not cancel_event.is_set():
            await asyncio.sleep(self._heartbeat_interval)
            if cancel_event.is_set():
                return
            with contextlib.suppress(RuntimeError):
                await updater.update_status(TaskState.working)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel a running task.

        Sets the cancel event to stop the heartbeat, cancels the in-flight
        asyncio task wrapping ``run_subagent()``, and emits a canceled status.

        Args:
            context: A2A request context providing the task and context IDs.
            event_queue: Queue used to emit the final canceled status event.
        """
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        updater = TaskUpdater(event_queue, task_id, context_id)
        logger.info("Cancelling task %s", task_id)
        async with self._tasks_lock:
            if event := self._cancel_events.get(task_id):
                event.set()
            if task := self._running_tasks.get(task_id):
                task.cancel()
        await updater.cancel()
