"""Team task engine for async team MCP tool operations.

Mirrors :class:`TaskEngine` from :mod:`vaultspec.orchestration.task_engine`
but wraps :class:`TeamCoordinator` dispatch operations instead of
``run_subagent()``.  Team tools submit work and receive a ``taskId``
immediately; callers poll via ``get_task_status()``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "TeamTask",
    "TeamTaskEngine",
    "TeamTaskStatus",
]

logger = logging.getLogger(__name__)


class TeamTaskStatus(StrEnum):
    """Lifecycle states for a team task."""

    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TeamTask:
    """In-memory record of a team MCP tool operation.

    Attributes:
        task_id: Unique identifier for this task.
        team_name: Name of the team the operation targets.
        operation: Human-readable label for the operation being performed.
        status: Current lifecycle state.
        created_at: Monotonic timestamp when the task was created.
        updated_at: Monotonic timestamp of the last status change.
        completed_at: Monotonic timestamp when the task reached a terminal
            state, or ``None`` if still in progress.
        result: Structured result payload set on successful completion.
        error: Error description set when the task fails.
        metadata: Arbitrary extra fields supplied at creation time.
    """

    task_id: str
    team_name: str
    operation: str
    status: TeamTaskStatus
    created_at: float
    updated_at: float
    completed_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TeamTaskEngine:
    """In-memory task engine for team MCP tool operations."""

    def __init__(self, ttl_seconds: float = 600.0) -> None:
        """Initialize the team task engine.

        Args:
            ttl_seconds: How long completed tasks are retained before being
                evicted from memory.
        """
        self._tasks: dict[str, TeamTask] = {}
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds
        self._bg_tasks: dict[str, asyncio.Task] = {}

    def _cleanup_expired(self) -> None:
        """Remove completed tasks that have exceeded the TTL retention window."""
        now = time.monotonic()
        expired = [
            tid
            for tid, task in self._tasks.items()
            if task.completed_at is not None
            and (now - task.completed_at) > self._ttl_seconds
        ]
        for tid in expired:
            self._tasks.pop(tid, None)
            self._bg_tasks.pop(tid, None)

    def create_task(
        self,
        team_name: str,
        operation: str,
        **metadata: Any,
    ) -> TeamTask:
        """Create a new team task in the WORKING state.

        Args:
            team_name: Name of the team the operation targets.
            operation: Human-readable label for the operation.
            **metadata: Arbitrary key-value pairs stored on the task.

        Returns:
            The newly created ``TeamTask``.
        """
        now = time.monotonic()
        task_id = str(uuid.uuid4())
        task = TeamTask(
            task_id=task_id,
            team_name=team_name,
            operation=operation,
            status=TeamTaskStatus.WORKING,
            created_at=now,
            updated_at=now,
            metadata=metadata,
        )
        with self._lock:
            self._cleanup_expired()
            self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> TeamTask | None:
        """Return the task with the given ID, or None if it does not exist.

        Args:
            task_id: The unique task identifier.

        Returns:
            The matching ``TeamTask``, or ``None``.
        """
        with self._lock:
            self._cleanup_expired()
            return self._tasks.get(task_id)

    def complete_task(self, task_id: str, result: dict[str, Any]) -> None:
        """Mark a task as successfully completed and store its result.

        A no-op if the task does not exist.

        Args:
            task_id: The unique task identifier.
            result: Structured result payload to attach to the task.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                logger.warning("complete_task called for unknown task_id=%s", task_id)
                return
            task.status = TeamTaskStatus.COMPLETED
            task.result = result
            now = time.monotonic()
            task.updated_at = now
            task.completed_at = now

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed and record the error message.

        A no-op if the task does not exist.

        Args:
            task_id: The unique task identifier.
            error: Human-readable description of the failure.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                logger.warning(
                    "fail_task: unknown task_id=%s (error=%s)", task_id, error
                )
                return
            task.status = TeamTaskStatus.FAILED
            task.error = error
            now = time.monotonic()
            task.updated_at = now
            task.completed_at = now

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task, also cancelling its associated background asyncio task if any.

        Args:
            task_id: The unique task identifier.

        Returns:
            ``True`` if the task was found and successfully cancelled;
            ``False`` if the task does not exist or is already terminal.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.completed_at is not None:
                return False
            task.status = TeamTaskStatus.CANCELLED
            now = time.monotonic()
            task.updated_at = now
            task.completed_at = now

        bg = self._bg_tasks.pop(task_id, None)
        if bg is not None and not bg.done():
            bg.cancel()
        return True

    def register_bg_task(self, task_id: str, bg: asyncio.Task) -> None:
        """Associate an asyncio background task with a team task for cancellation
        support.

        Args:
            task_id: The unique team task identifier.
            bg: The asyncio ``Task`` running the background operation.
        """
        with self._lock:
            self._bg_tasks[task_id] = bg

    def list_tasks(self) -> list[TeamTask]:
        """Return all non-expired tasks.

        Returns:
            List of all currently tracked ``TeamTask`` instances.
        """
        with self._lock:
            self._cleanup_expired()
            return list(self._tasks.values())
