"""Internal task engine for the dispatch framework.

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

logger = logging.getLogger(__name__)


class TaskStatus(StrEnum):
    """Lifecycle states for a dispatch task."""

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
    """True if the status represents a final, immutable state."""
    return status in (
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    )


@dataclass
class DispatchTask:
    """In-memory representation of a background sub-agent execution."""

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
    """Generate a unique identifier for a new task."""
    return str(uuid.uuid4())


class LockManager:
    """Advisory lock manager for workspace coordination (Phase 4).

    Rule:
    - read-only tasks may only write to .docs/ paths.
    - read-write tasks have no path restrictions.
    """

    # Paths allowed for read-only mode (workspace-relative prefixes).
    READONLY_ALLOWED_PREFIXES = (".docs/",)

    def __init__(self) -> None:
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
        """Release the advisory lock held by a task."""
        with self._lock:
            return self._locks.pop(task_id, None) is not None

    def check_conflicts(self, paths: set[str]) -> list[str]:
        """Check if paths conflict with active locks."""
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
        """Get the lock held by a specific task, or None."""
        with self._lock:
            return self._locks.get(task_id)

    def get_locks(self) -> list[FileLock]:
        """Return all active advisory locks."""
        with self._lock:
            return list(self._locks.values())

    @staticmethod
    def validate_readonly_paths(paths: set[str]) -> list[str]:
        """Validate paths are in the read-only zone."""
        violations: list[str] = []
        for path in paths:
            normalized = path.replace("", "/")
            if not any(
                normalized.startswith(prefix)
                for prefix in LockManager.READONLY_ALLOWED_PREFIXES
            ):
                violations.append(path)
        return violations


class TaskEngine:
    """In-memory task engine with thread-safe access."""

    def __init__(
        self,
        ttl_seconds: float = 3600.0,
        lock_manager: LockManager | None = None,
    ) -> None:
        """Initialize the task engine.

        Args:
            ttl_seconds: Retention period.
            lock_manager: LockManager for automatic release.
        """
        self._tasks: dict[str, DispatchTask] = {}
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds
        self._lock_manager = lock_manager
        self._expiry: dict[str, float] = {}
        self._events: dict[str, asyncio.Event] = {}

    def _release_lock(self, task_id: str) -> None:
        """Release advisory lock for a task."""
        if self._lock_manager is not None:
            released = self._lock_manager.release_lock(task_id)
            if released:
                logger.debug("Released advisory lock for task %s", task_id)

    def _cleanup_expired(self) -> None:
        """Remove tasks that have exceeded their TTL."""
        now = time.monotonic()
        expired = [tid for tid, exp in self._expiry.items() if now >= exp]
        for tid in expired:
            self._release_lock(tid)
            self._tasks.pop(tid, None)
            self._expiry.pop(tid, None)
            self._events.pop(tid, None)

    def create_task(
        self,
        agent: str,
        *,
        model: str | None = None,
        mode: str = "read-write",
        task_id: str | None = None,
    ) -> DispatchTask:
        """Create a new task."""
        tid = task_id or generate_task_id()
        now = time.monotonic()

        task = DispatchTask(
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

    def get_task(self, task_id: str) -> DispatchTask | None:
        """Get a task by ID."""
        with self._lock:
            self._cleanup_expired()
            return self._tasks.get(task_id)

    def set_session_id(self, task_id: str, session_id: str) -> None:
        """Store the ACP session ID."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")
            task.session_id = session_id
            task.updated_at = time.monotonic()

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        status_message: str | None = None,
    ) -> DispatchTask:
        """Transition a task to a new status."""
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
                self._expiry[task_id] = time.monotonic() + self._ttl_seconds
                self._release_lock(task_id)

        # Notify any async waiters outside the lock.
        self._notify(task_id)

        return task

    def complete_task(
        self,
        task_id: str,
        result: dict[str, Any],
    ) -> DispatchTask:
        """Mark a task as completed."""
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
            task.result = result
            self._expiry[task_id] = time.monotonic() + self._ttl_seconds
            self._release_lock(task_id)

        self._notify(task_id)
        return task

    def fail_task(
        self,
        task_id: str,
        error: str,
    ) -> DispatchTask:
        """Mark a task as failed."""
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
            task.error = error
            self._expiry[task_id] = time.monotonic() + self._ttl_seconds
            self._release_lock(task_id)

        self._notify(task_id)
        return task

    def cancel_task(self, task_id: str) -> DispatchTask:
        """Cancel a task."""
        return self.update_status(task_id, TaskStatus.CANCELLED)

    def list_tasks(self) -> list[DispatchTask]:
        """Return all non-expired tasks."""
        with self._lock:
            self._cleanup_expired()
            return list(self._tasks.values())

    def delete_task(self, task_id: str) -> bool:
        """Remove a task from the engine entirely."""
        with self._lock:
            removed = self._tasks.pop(task_id, None) is not None
            self._expiry.pop(task_id, None)
            self._events.pop(task_id, None)
        return removed

    # -- Async wait/notify --

    async def wait_for_update(self, task_id: str, timeout: float | None = None) -> None:
        """Wait until the task's status changes."""
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
        """Wake up any coroutine waiting on this task."""
        with self._lock:
            event = self._events.pop(task_id, None)
        if event is not None:
            event.set()
