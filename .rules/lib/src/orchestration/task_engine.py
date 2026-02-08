"""Internal task engine for the dispatch framework.

A standalone 5-state task lifecycle manager with no MCP or ACP dependencies.
Tracks: working -> input_required | completed | failed | cancelled.

State machine per ADR dispatch-task-contract Decision 1:

    working --+--> completed
              |
              +--> input_required --+--> working (resumed)
              |
              +--> failed
              |
              +--> cancelled

Also provides advisory file locking for workspace coordination
(ADR dispatch-workspace-safety Decision 1).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("pp-dispatch.task-engine")


class TaskStatus(str, Enum):
    """5-state task lifecycle."""

    WORKING = "working"
    INPUT_REQUIRED = "input_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Terminal states: no further transitions allowed.
TERMINAL_STATES = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }
)

# Valid transitions from each state.
_VALID_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.WORKING: frozenset(
        {
            TaskStatus.INPUT_REQUIRED,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.INPUT_REQUIRED: frozenset(
        {
            TaskStatus.WORKING,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    # Terminal states cannot transition.
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


class InvalidTransitionError(Exception):
    """Raised when a state transition violates the task lifecycle rules."""


class TaskNotFoundError(Exception):
    """Raised when a task ID is not found in the engine."""


class LockConflictError(Exception):
    """Raised when advisory lock acquisition conflicts with an active lock."""


@dataclass
class DispatchTask:
    """Dispatch-specific task metadata and state.

    Fields:
        task_id: UUID string identifying this task.
        agent: Agent name from .rules/agents/.
        status: Current lifecycle state.
        created_at: Monotonic timestamp of task creation.
        updated_at: Monotonic timestamp of last state change.
        model: Model override (or None for agent default).
        mode: Permission mode -- 'read-write' or 'read-only'.
        result: Structured result dict on completion.
        error: Error message string on failure.
        status_message: Optional human-readable status description.
        session_id: ACP session ID for session resume (or None).
    """

    task_id: str
    agent: str
    status: TaskStatus
    created_at: float
    updated_at: float
    model: str | None = None
    mode: str = "read-write"
    result: dict[str, Any] | None = None
    error: str | None = None
    status_message: str | None = None
    session_id: str | None = None


def is_terminal(status: TaskStatus) -> bool:
    """Check if a status represents a terminal (final) state."""
    return status in TERMINAL_STATES


def generate_task_id() -> str:
    """Generate a unique task ID (UUID4)."""
    return str(uuid.uuid4())


@dataclass
class FileLock:
    """Advisory file lock held by a dispatch task.

    Per ADR dispatch-workspace-safety Decision 1, locks are in-memory and
    advisory (logged warnings, not OS-enforced).

    Fields:
        task_id: The owning task's UUID.
        paths: Set of workspace-relative paths this task intends to write.
        mode: Permission mode -- 'read-write' or 'read-only'.
        acquired_at: Monotonic timestamp when the lock was acquired.
    """

    task_id: str
    paths: frozenset[str]
    mode: str
    acquired_at: float


class LockManager:
    """Advisory file lock manager for workspace coordination.

    Tracks which paths each active task intends to write to.  Detects
    conflicts when two tasks target overlapping paths.  All state is
    in-memory with thread-safe access.

    Per ADR dispatch-workspace-safety Decision 1:
    - Lock state is in-memory (no filesystem lock files).
    - Locks are advisory (logged warnings, not OS-enforced).
    - read-only tasks may only write to ``.docs/`` paths.
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
            paths: Set of workspace-relative paths the task intends to write.
            mode: Permission mode ('read-write' or 'read-only').

        Returns:
            A tuple of (acquired FileLock, list of conflict warning strings).
            Conflicts are advisory -- the lock is still acquired.

        Raises:
            ValueError: If task_id already holds a lock.
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
                    warnings.append(
                        f"Path conflict with task {existing.task_id}: "
                        f"{', '.join(sorted(overlap))}"
                    )

            self._locks[task_id] = lock

        return lock, warnings

    def release_lock(self, task_id: str) -> bool:
        """Release the advisory lock held by a task.

        Args:
            task_id: The task releasing its lock.

        Returns:
            True if a lock was found and released, False otherwise.
        """
        with self._lock:
            return self._locks.pop(task_id, None) is not None

    def check_conflicts(self, paths: set[str]) -> list[str]:
        """Check if the given paths conflict with any active locks.

        Args:
            paths: Set of workspace-relative paths to check.

        Returns:
            List of conflict description strings (empty if no conflicts).
        """
        frozen = frozenset(paths)
        conflicts: list[str] = []

        with self._lock:
            for existing in self._locks.values():
                overlap = frozen & existing.paths
                if overlap:
                    conflicts.append(
                        f"Conflict with task {existing.task_id} "
                        f"(mode={existing.mode}): "
                        f"{', '.join(sorted(overlap))}"
                    )

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
        """Validate that all paths are within the read-only allowed zone.

        Args:
            paths: Set of workspace-relative paths to validate.

        Returns:
            List of paths that violate the read-only restriction.
        """
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
    """In-memory task engine with thread-safe access and TTL-based expiry.

    This is the Layer 2 component: it owns task lifecycle, state transitions,
    and result storage. It has no MCP or ACP dependencies.

    Concurrency: Uses a threading.Lock for dict mutations (safe from both
    sync and async callers). Async waiters use asyncio.Event per task.
    """

    def __init__(
        self,
        ttl_seconds: float = 3600.0,
        lock_manager: LockManager | None = None,
    ) -> None:
        """Initialize the task engine.

        Args:
            ttl_seconds: How long to retain completed/failed/cancelled tasks
                before expiry cleanup. Default 1 hour.
            lock_manager: Optional LockManager for automatic lock release
                on terminal state transitions.
        """
        self._tasks: dict[str, DispatchTask] = {}
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds
        self._lock_manager = lock_manager
        # Monotonic timestamp when a terminal task should be removed.
        self._expiry: dict[str, float] = {}
        # Async events for waiters (get_task_status polling).
        self._events: dict[str, asyncio.Event] = {}

    def _release_lock(self, task_id: str) -> None:
        """Release advisory lock for a task if a lock manager is configured.

        Called on terminal state transitions. Safe to call even if no lock
        exists for this task (release_lock returns False silently).
        """
        if self._lock_manager is not None:
            released = self._lock_manager.release_lock(task_id)
            if released:
                logger.debug("Released advisory lock for task %s", task_id)

    def _cleanup_expired(self) -> None:
        """Remove tasks that have exceeded their TTL. Called lazily on access."""
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
        """Create a new task in the 'working' state.

        Args:
            agent: Agent name.
            model: Optional model override.
            mode: Permission mode.
            task_id: Optional pre-generated ID (UUID generated if None).

        Returns:
            The created DispatchTask.

        Raises:
            ValueError: If the task_id already exists.
        """
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
        """Get a task by ID, or None if not found (or expired)."""
        with self._lock:
            self._cleanup_expired()
            return self._tasks.get(task_id)

    def set_session_id(self, task_id: str, session_id: str) -> None:
        """Store the ACP session ID on a task for potential session resume.

        Args:
            task_id: The task to update.
            session_id: The ACP session ID to store.

        Raises:
            TaskNotFoundError: If task_id is not found.
        """
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
        """Transition a task to a new status.

        Args:
            task_id: The task to update.
            status: The new status.
            status_message: Optional human-readable message.

        Returns:
            The updated DispatchTask.

        Raises:
            TaskNotFoundError: If task_id is not found.
            InvalidTransitionError: If the transition violates lifecycle rules.
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
        """Mark a task as completed with a structured result.

        Args:
            task_id: The task to complete.
            result: Structured result dict (per ADR schema).

        Returns:
            The updated DispatchTask.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            allowed = _VALID_TRANSITIONS[task.status]
            if TaskStatus.COMPLETED not in allowed:
                raise InvalidTransitionError(
                    f"Cannot complete task in '{task.status.value}' state"
                )

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
        """Mark a task as failed with an error message.

        Args:
            task_id: The task to fail.
            error: Human-readable error description.

        Returns:
            The updated DispatchTask.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            allowed = _VALID_TRANSITIONS[task.status]
            if TaskStatus.FAILED not in allowed:
                raise InvalidTransitionError(
                    f"Cannot fail task in '{task.status.value}' state"
                )

            task.status = TaskStatus.FAILED
            task.updated_at = time.monotonic()
            task.error = error
            self._expiry[task_id] = time.monotonic() + self._ttl_seconds
            self._release_lock(task_id)

        self._notify(task_id)
        return task

    def cancel_task(self, task_id: str) -> DispatchTask:
        """Cancel a task (must not be in a terminal state).

        Args:
            task_id: The task to cancel.

        Returns:
            The updated DispatchTask.

        Raises:
            TaskNotFoundError: If task_id is not found.
            InvalidTransitionError: If the task is already in a terminal state.
        """
        return self.update_status(task_id, TaskStatus.CANCELLED)

    def list_tasks(self) -> list[DispatchTask]:
        """Return all non-expired tasks."""
        with self._lock:
            self._cleanup_expired()
            return list(self._tasks.values())

    def delete_task(self, task_id: str) -> bool:
        """Remove a task from the engine entirely.

        Returns:
            True if the task was found and deleted.
        """
        with self._lock:
            removed = self._tasks.pop(task_id, None) is not None
            self._expiry.pop(task_id, None)
            self._events.pop(task_id, None)
        return removed

    # -- Async wait/notify for status polling --

    async def wait_for_update(self, task_id: str, timeout: float | None = None) -> None:
        """Wait until the task's status changes.

        Args:
            task_id: The task to watch.
            timeout: Maximum seconds to wait (None = wait indefinitely).

        Raises:
            TaskNotFoundError: If task_id is not found.
            asyncio.TimeoutError: If timeout is exceeded.
        """
        with self._lock:
            if task_id not in self._tasks:
                raise TaskNotFoundError(f"Task not found: {task_id}")
            # NOTE: Only one waiter per task_id is supported. A second call
            # overwrites the first waiter's event, leaving it blocked forever.
            # NOTE: asyncio.Event is bound to the current event loop. Callers
            # must share the same loop as _notify() (true for MCP server usage).
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
