"""Base executor utilities shared across A2A executors.

Provides `BaseA2AExecutor` which implements standard task mechanics:
- Exponential backoff retries for rate limits
- Cancellation and error handling
- Concurrency locks and active task tracking
"""

from __future__ import annotations

import abc
import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from a2a.server.events import EventQueue

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TaskState, TextPart

__all__ = [
    "BaseA2AExecutor",
]


class BaseA2AExecutor(AgentExecutor, abc.ABC):
    """Abstract base executor providing shared task governance.

    Subclasses must implement `_run_stream` to perform the actual provider SDK
    or CLI interaction.

    Args:
        max_retries: Maximum number of retries on retryable errors before failing.
        retry_base_delay: Base delay in seconds for exponential back-off between retries.
    """

    def __init__(
        self,
        *,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ) -> None:
        """Initialize the base executor with retry and task tracking constraints."""
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

        # Shared concurrency tracking
        self._active_tasks: dict[str, Any] = {}
        self._tasks_lock = asyncio.Lock()
        self._cancel_events: dict[str, asyncio.Event] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute an A2A task with automatic retry and cancellation handling.

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
            "BaseA2AExecutor starting task %s (context=%s)",
            task_id,
            context_id,
        )

        cancel_event = asyncio.Event()
        self._cancel_events[task_id] = cancel_event

        cancelled = False
        errored = False
        try:
            # Subclass hook for any per-task initialization (e.g. SDK connection)
            await self._on_task_start(task_id, context_id, cancel_event)

            # Signal working after subclass init ensures we are truly running
            await updater.start_work()

            attempt = 0
            while True:
                should_retry = await self._run_stream(
                    prompt=prompt,
                    updater=updater,
                    context_id=context_id,
                    task_id=task_id,
                    cancel_event=cancel_event,
                )
                if cancel_event.is_set():
                    cancelled = True
                    with contextlib.suppress(RuntimeError):
                        await updater.cancel()
                    break
                if not should_retry:
                    break

                # Rate-limit retry with exponential back-off.
                attempt += 1
                if attempt > self._max_retries:
                    await updater.failed(
                        message=updater.new_agent_message(
                            parts=[
                                Part(
                                    root=TextPart(
                                        text=f"Rate limited: exhausted {self._max_retries} retries"
                                    )
                                )
                            ]
                        )
                    )
                    break

                delay = self._retry_base_delay * (2**attempt)
                await updater.update_status(
                    TaskState.working,
                    message=updater.new_agent_message(
                        parts=[
                            Part(
                                root=TextPart(
                                    text=f"Rate limited, retrying (attempt {attempt}/{self._max_retries})"
                                )
                            )
                        ]
                    ),
                )
                logger.info(
                    "Rate limited on task %s, retrying in %.1fs (attempt %d/%d)",
                    task_id,
                    delay,
                    attempt,
                    self._max_retries,
                )
                await asyncio.sleep(delay)

        except Exception as e:
            errored = True
            logger.exception("BaseA2AExecutor error for task %s", task_id)
            await updater.failed(
                message=updater.new_agent_message(
                    parts=[Part(root=TextPart(text=str(e)))]
                )
            )
        finally:
            self._cancel_events.pop(task_id, None)
            await self._on_task_end(
                task_id, context_id, cancelled=cancelled, errored=errored
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel a running A2A task by signaling the loop.

        Args:
            context: The A2A request context carrying the task ID to cancel.
            event_queue: The A2A event queue used to emit the cancelled status.
        """
        task_id = context.task_id or ""
        context_id = context.context_id or ""

        cancel_event = self._cancel_events.get(task_id)
        in_flight = cancel_event is not None
        if cancel_event is not None:
            cancel_event.set()

        await self._on_task_cancel(task_id, context_id)

        if in_flight:
            updater = TaskUpdater(event_queue, task_id, context_id)
            with contextlib.suppress(RuntimeError):
                await updater.cancel()

    async def cleanup(self) -> None:
        """Cleanup hook for server shutdown."""
        await self._on_cleanup()

    # --- Subclass Hooks ---

    async def _on_task_start(
        self, task_id: str, context_id: str, cancel_event: asyncio.Event
    ) -> None:
        """Hook called before the task loop begins (e.g. SDK connection)."""
        pass

    @abc.abstractmethod
    async def _run_stream(
        self,
        *,
        prompt: str,
        updater: TaskUpdater,
        context_id: str,
        task_id: str,
        cancel_event: asyncio.Event,
    ) -> bool:
        """Execute one query+stream cycle. Must return True if a retryable
        rate limit error occurs.
        """
        pass

    async def _on_task_end(
        self, task_id: str, context_id: str, cancelled: bool, errored: bool
    ) -> None:
        """Hook called after the task loop finishes or faults (e.g. client teardown)."""
        pass

    async def _on_task_cancel(self, task_id: str, context_id: str) -> None:
        """Hook called when the cancellation signal is fired (e.g. interrupt client)."""
        pass

    async def _on_cleanup(self) -> None:
        """Hook called on server teardown (e.g. destroy all clients)."""
        pass
