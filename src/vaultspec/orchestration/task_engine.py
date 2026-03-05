"""Internal task engine for the subagent framework.

A standalone 5-state task lifecycle manager.
Tracks tasks: working -> input_required | completed | failed | cancelled.

State machine per ADR dispatch-task-contract Decision 1:

    working --+--> completed
              |
              +--> input_required --+--> working (resumed)
              |                     |
              |                     +--> cancelled
              |
              +--> failed
              |
              +--> cancelled
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

__all__ = [
    "FileLock",
    "InvalidTransitionError",
    "LockManager",
    "SubagentTask",
    "TaskEngine",
    "TaskNotFoundError",
    "TaskStatus",
    "generate_task_id",
    "is_terminal",
]

logger = logging.getLogger(__name__)


class TaskStatus(StrEnum):
    """Lifecycle states for a subagent task."""

    WORKING = "working"
    INPUT_REQUIRED = "input_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Valid state transitions
_VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.WORKING: {
        TaskStatus.INPUT_REQUIRED,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.INPUT_REQUIRED: {
        TaskStatus.WORKING,
        TaskStatus.CANCELLED,
    },
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


def is_terminal(status: TaskStatus) -> bool:
    """Return whether a status represents a final, immutable state.

    Args:
        status: The ``TaskStatus`` value to test.

    Returns:
        ``True`` if ``status`` is ``COMPLETED``, ``FAILED``, or ``CANCELLED``;
        ``False`` otherwise.
    """
    return status in (
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    )


@dataclass
class SubagentTask:
    """In-memory representation of a background sub-agent execution.

    Attributes:
        task_id: Unique identifier for this task.
        agent: Name of the agent executing the task.
        status: Current lifecycle state.
        created_at: Monotonic timestamp at task creation.
        updated_at: Monotonic timestamp of the last status change.
        completed_at: Monotonic timestamp when the task reached a terminal
            state, or ``None`` if still in progress.
        model: Optional model override for the agent.
        mode: Permission mode, either ``'read-write'`` or ``'read-only'``.
        status_message: Optional human-readable status description.
        result: Structured result payload set on successful completion.
        error: Error description set when the task fails.
        session_id: ACP internal session identifier, if one has been assigned.
    """

    task_id: str
    agent: str
    status: TaskStatus
    created_at: float  # monotonic
    updated_at: float  # monotonic
    completed_at: float | None = None
    model: str | None = None
    mode: str = "read-write"
    status_message: str | None = None
    # Result or error payload
    result: dict[str, Any] | None = None
    error: str | None = None
    # ACP internal state
    session_id: str | None = None


@dataclass(frozen=True)
class FileLock:
    """Advisory write intent for workspace paths."""

    task_id: str
    paths: frozenset[str]
    mode: str
    acquired_at: float


class TaskNotFoundError(Exception):
    """Raised when a requested task ID is unknown or expired."""

    pass


class InvalidTransitionError(Exception):
    """Raised when a state transition violates lifecycle rules."""

    pass


def generate_task_id() -> str:
    """Generate a unique identifier for a new task.

    Returns:
        A random UUID4 string.
    """
    return str(uuid.uuid4())


class LockManager:
    """Advisory lock manager for workspace coordination (Phase 4).

    Rule:
    - read-only tasks may only write to .vault/ paths.
    - read-write tasks have no path restrictions.
    """

    @staticmethod
    def _readonly_allowed_prefixes() -> tuple[str, ...]:
        """Return the workspace-relative path prefixes permitted for read-only tasks.

        Returns:
            A tuple of allowed prefix strings (e.g. ``(".vault/",)``).
        """
        from ..config import get_config

        return (f"{get_config().docs_dir}/",)

    def __init__(self) -> None:
        """Initialize the LockManager with an empty advisory lock registry."""
        self._locks: dict[str, FileLock] = {}
        self._lock = threading.Lock()

    def acquire_lock(
        self,
        task_id: str,
        paths: set[str],
        mode: str,
    ) -> tuple[FileLock, list[str]]:
        """Register write intent for a task.

        Args:
            task_id: The task acquiring the lock.
            paths: Set of workspace-relative paths.
            mode: Permission mode ('read-write' or 'read-only').

        Returns:
            A tuple of (acquired FileLock, list of conflict strings).
        """
        now = time.monotonic()
        frozen_paths = frozenset(paths)
        lock = FileLock(
            task_id=task_id,
            paths=frozen_paths,
            mode=mode,
            acquired_at=now,
        )

        warnings: list[str] = []

        with self._lock:
            if task_id in self._locks:
                raise ValueError(f"Task {task_id} already holds a lock")

            # Check for path conflicts with existing locks.
            for existing in self._locks.values():
                overlap = frozen_paths & existing.paths
                if overlap:
                    msg = (
                        f"Conflict with {existing.task_id}: "
                        f"{', '.join(sorted(overlap))}"
                    )
                    warnings.append(msg)

            self._locks[task_id] = lock

        return lock, warnings

    def release_lock(self, task_id: str) -> bool:
        """Release the advisory lock held by a task.

        Args:
            task_id: The task whose lock should be released.

        Returns:
            ``True`` if a lock was found and removed; ``False`` otherwise.
        """
        with self._lock:
            return self._locks.pop(task_id, None) is not None

    def check_conflicts(self, paths: set[str]) -> list[str]:
        """Check whether any of the given paths conflict with active advisory locks.

        Args:
            paths: Workspace-relative paths to check.

        Returns:
            List of human-readable conflict descriptions; empty if no conflicts.
        """
        frozen = frozenset(paths)
        conflicts: list[str] = []

        with self._lock:
            for existing in self._locks.values():
                overlap = frozen & existing.paths
                if overlap:
                    msg = (
                        f"Conflict with task {existing.task_id} "
                        f"(mode={existing.mode}): "
                        f"{', '.join(sorted(overlap))}"
                    )
                    conflicts.append(msg)

        return conflicts

    def get_lock(self, task_id: str) -> FileLock | None:
        """Return the advisory lock held by the given task, or None if not found.

        Args:
            task_id: The task whose lock to retrieve.

        Returns:
            The ``FileLock``, or ``None``.
        """
        with self._lock:
            return self._locks.get(task_id)

    def get_locks(self) -> list[FileLock]:
        """Return a snapshot of all currently active advisory locks.

        Returns:
            List of all held ``FileLock`` instances.
        """
        with self._lock:
            return list(self._locks.values())

    @staticmethod
    def validate_readonly_paths(paths: set[str]) -> list[str]:
        """Return paths that violate the read-only zone restriction.

        Read-only tasks may only write to the ``.vault/`` directory.  Any path
        that does not start with the allowed prefix is a violation.

        Args:
            paths: Workspace-relative paths to validate.

        Returns:
            List of violating paths; empty if all paths are permitted.
        """
        violations: list[str] = []
        for path in paths:
            normalized = path.replace("\\", "/")
            if not any(
                normalized.startswith(prefix)
                for prefix in LockManager._readonly_allowed_prefixes()
            ):
                violations.append(path)
        return violations


class TaskEngine:
    """In-memory task engine with thread-safe access."""

    def __init__(
        self,
        ttl_seconds: float | None = None,
        lock_manager: LockManager | None = None,
        max_working_seconds: float = 600,
    ) -> None:
        """Initialize the task engine.

        Args:
            ttl_seconds: Retention period.  Defaults to config value.
            lock_manager: LockManager for automatic release.
            max_working_seconds: Max time a task may stay in WORKING state.
        """
        if ttl_seconds is None:
            from ..config import get_config

            ttl_seconds = get_config().task_engine_ttl_seconds
        self._tasks: dict[str, SubagentTask] = {}
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds
        self._max_working_seconds = max_working_seconds
        self._lock_manager = lock_manager
        self._expiry: dict[str, float] = {}
        self._events: dict[str, asyncio.Event] = {}

    def _release_lock(self, task_id: str) -> None:
        """Release advisory lock for a task.

        Args:
            task_id: The task whose advisory lock should be released.
        """
        if self._lock_manager is not None:
            released = self._lock_manager.release_lock(task_id)
            if released:
                logger.debug(f"Released advisory lock for task {task_id}")

    def _cleanup_expired(self) -> None:
        """Remove tasks past their TTL and fail tasks stuck in WORKING state."""
        now = time.monotonic()
        expired = [tid for tid, exp in self._expiry.items() if now >= exp]
        for tid in expired:
            self._release_lock(tid)
            self._tasks.pop(tid, None)
            self._expiry.pop(tid, None)
            self._events.pop(tid, None)

        # Evict WORKING tasks that exceed the maximum allowed duration.
        stuck = [
            tid
            for tid, task in self._tasks.items()
            if task.status == TaskStatus.WORKING
            and (now - task.created_at) > self._max_working_seconds
        ]
        for tid in stuck:
            task = self._tasks[tid]
            task.status = TaskStatus.FAILED
            task.error = "Task exceeded max working time"
            task.updated_at = now
            task.completed_at = now
            self._expiry[tid] = now + self._ttl_seconds
            self._release_lock(tid)
            logger.warning("Evicted stuck WORKING task %s (agent=%s)", tid, task.agent)

    def create_task(
        self,
        agent: str,
        *,
        model: str | None = None,
        mode: str = "read-write",
        task_id: str | None = None,
    ) -> SubagentTask:
        """Create a new task in the WORKING state.

        Args:
            agent: Name of the agent that will execute the task.
            model: Optional model override for the agent.
            mode: Permission mode, either ``'read-write'`` or ``'read-only'``.
            task_id: Optional explicit task ID; generated if not provided.

        Returns:
            The newly created ``SubagentTask``.

        Raises:
            ValueError: If a task with the given ``task_id`` already exists.
        """
        tid = task_id or generate_task_id()
        now = time.monotonic()

        task = SubagentTask(
            task_id=tid,
            agent=agent,
            status=TaskStatus.WORKING,
            created_at=now,
            updated_at=now,
            model=model,
            mode=mode,
        )

        with self._lock:
            self._cleanup_expired()
            if tid in self._tasks:
                raise ValueError(f"Task with ID {tid} already exists")
            self._tasks[tid] = task

        return task

    def get_task(self, task_id: str) -> SubagentTask | None:
        """Return the task with the given ID, or None if not found or expired.

        Args:
            task_id: The unique task identifier.

        Returns:
            The matching ``SubagentTask``, or ``None``.
        """
        with self._lock:
            self._cleanup_expired()
            return self._tasks.get(task_id)

    def set_session_id(self, task_id: str, session_id: str) -> None:
        """Store the ACP session ID associated with a task.

        Args:
            task_id: The unique task identifier.
            session_id: The ACP session ID to store.

        Raises:
            TaskNotFoundError: If the task does not exist.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")
            task.session_id = session_id
            task.updated_at = time.monotonic()

    def get_session_id(self, task_id: str) -> str | None:
        """Retrieve the stored ACP session ID for a task, if any.

        Args:
            task_id: The unique task identifier.

        Returns:
            The ACP session ID, or ``None`` if the task is not found or has
            no session ID recorded.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            return task.session_id

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        status_message: str | None = None,
    ) -> SubagentTask:
        """Transition a task to a new lifecycle status.

        Args:
            task_id: The unique task identifier.
            status: The target ``TaskStatus``.
            status_message: Optional human-readable message describing the
                status change.

        Returns:
            The updated ``SubagentTask``.

        Raises:
            TaskNotFoundError: If the task does not exist.
            InvalidTransitionError: If the requested transition is not allowed
                by the lifecycle state machine.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            if status != task.status:
                allowed = _VALID_TRANSITIONS[task.status]
                if status not in allowed:
                    msg = (
                        f"Cannot transition from '{task.status.value}' "
                        f"to '{status.value}'"
                    )
                    raise InvalidTransitionError(msg)

            task.status = status
            task.updated_at = time.monotonic()

            if status_message is not None:
                task.status_message = status_message

            # Set TTL expiry and release lock for terminal states.
            if is_terminal(status):
                task.completed_at = task.updated_at
                self._expiry[task_id] = task.updated_at + self._ttl_seconds
                self._release_lock(task_id)

        # Notify any async waiters outside the lock.
        self._notify(task_id)

        return task

    def complete_task(
        self,
        task_id: str,
        result: dict[str, Any],
    ) -> SubagentTask:
        """Mark a task as completed and attach its result payload.

        Args:
            task_id: The unique task identifier.
            result: Structured result data to store on the task.

        Returns:
            The updated ``SubagentTask``.

        Raises:
            TaskNotFoundError: If the task does not exist.
            InvalidTransitionError: If the task cannot transition to COMPLETED
                from its current state.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            allowed = _VALID_TRANSITIONS[task.status]
            if TaskStatus.COMPLETED not in allowed:
                msg = f"Cannot complete task in '{task.status.value}' state"
                raise InvalidTransitionError(msg)

            task.status = TaskStatus.COMPLETED
            task.updated_at = time.monotonic()
            task.completed_at = task.updated_at
            task.result = result
            self._expiry[task_id] = time.monotonic() + self._ttl_seconds
            self._release_lock(task_id)

        self._notify(task_id)
        return task

    def fail_task(
        self,
        task_id: str,
        error: str,
    ) -> SubagentTask:
        """Mark a task as failed and record the error description.

        Args:
            task_id: The unique task identifier.
            error: Human-readable description of the failure.

        Returns:
            The updated ``SubagentTask``.

        Raises:
            TaskNotFoundError: If the task does not exist.
            InvalidTransitionError: If the task cannot transition to FAILED
                from its current state.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            allowed = _VALID_TRANSITIONS[task.status]
            if TaskStatus.FAILED not in allowed:
                msg = f"Cannot fail task in '{task.status.value}' state"
                raise InvalidTransitionError(msg)

            task.status = TaskStatus.FAILED
            task.updated_at = time.monotonic()
            task.completed_at = task.updated_at
            task.error = error
            self._expiry[task_id] = time.monotonic() + self._ttl_seconds
            self._release_lock(task_id)

        self._notify(task_id)
        return task

    def cancel_task(self, task_id: str) -> SubagentTask:
        """Transition a task to the CANCELLED state.

        Args:
            task_id: The unique task identifier.

        Returns:
            The updated ``SubagentTask``.

        Raises:
            TaskNotFoundError: If the task does not exist.
            InvalidTransitionError: If the task cannot be cancelled from its
                current state.
        """
        return self.update_status(task_id, TaskStatus.CANCELLED)

    def list_tasks(self) -> list[SubagentTask]:
        """Return all tasks that have not yet been evicted by the TTL.

        Returns:
            List of currently tracked ``SubagentTask`` instances.
        """
        with self._lock:
            self._cleanup_expired()
            return list(self._tasks.values())

    def delete_task(self, task_id: str) -> bool:
        """Remove a task from the engine regardless of its current state.

        Args:
            task_id: The unique task identifier.

        Returns:
            ``True`` if the task existed and was removed; ``False`` otherwise.
        """
        with self._lock:
            removed = self._tasks.pop(task_id, None) is not None
            self._expiry.pop(task_id, None)
            self._events.pop(task_id, None)
        return removed

    # -- Async wait/notify --

    async def wait_for_update(self, task_id: str, timeout: float | None = None) -> None:
        """Suspend until the task's status changes or the timeout elapses.

        Args:
            task_id: The unique task identifier.
            timeout: Maximum seconds to wait.  Waits indefinitely if ``None``.

        Raises:
            TaskNotFoundError: If the task does not exist.
            asyncio.TimeoutError: If the timeout expires before a status change.
        """
        with self._lock:
            if task_id not in self._tasks:
                raise TaskNotFoundError(f"Task not found: {task_id}")
            event = asyncio.Event()
            self._events[task_id] = event

        if timeout is not None:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        else:
            await event.wait()

    def _notify(self, task_id: str) -> None:
        """Wake up any coroutine waiting on this task.

        Must be called from the event loop thread
        (asyncio.Event.set is not thread-safe).

        Args:
            task_id: The task whose waiters should be notified.
        """
        with self._lock:
            event = self._events.pop(task_id, None)
        if event is not None:
            event.set()
