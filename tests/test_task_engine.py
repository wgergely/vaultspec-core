from __future__ import annotations

import pathlib
import sys

# Ensure scripts dir is importable
_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import asyncio  # noqa: E402
import time  # noqa: E402

import pytest  # noqa: E402

from task_engine import (  # noqa: E402
    InvalidTransitionError,
    LockManager,
    TaskEngine,
    TaskNotFoundError,
    TaskStatus,
    generate_task_id,
    is_terminal,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    """Fresh TaskEngine for each test."""
    return TaskEngine(ttl_seconds=3600.0)


@pytest.fixture
def short_ttl_engine():
    """TaskEngine with very short TTL for expiry tests."""
    return TaskEngine(ttl_seconds=0.1)


@pytest.fixture
def lock_mgr():
    """Fresh LockManager for each test."""
    return LockManager()


@pytest.fixture
def engine_with_locks():
    """TaskEngine wired to a LockManager for lock-lifecycle tests."""
    lm = LockManager()
    eng = TaskEngine(ttl_seconds=3600.0, lock_manager=lm)
    return eng, lm


@pytest.fixture
def short_ttl_engine_with_locks():
    """TaskEngine with short TTL wired to a LockManager."""
    lm = LockManager()
    eng = TaskEngine(ttl_seconds=0.1, lock_manager=lm)
    return eng, lm


# ---------------------------------------------------------------------------
# TestHelpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_generate_task_id_unique(self):
        ids = {generate_task_id() for _ in range(100)}
        assert len(ids) == 100

    def test_is_terminal_completed(self):
        assert is_terminal(TaskStatus.COMPLETED) is True

    def test_is_terminal_failed(self):
        assert is_terminal(TaskStatus.FAILED) is True

    def test_is_terminal_cancelled(self):
        assert is_terminal(TaskStatus.CANCELLED) is True

    def test_is_terminal_working(self):
        assert is_terminal(TaskStatus.WORKING) is False

    def test_is_terminal_input_required(self):
        assert is_terminal(TaskStatus.INPUT_REQUIRED) is False


# ---------------------------------------------------------------------------
# TestCreateTask
# ---------------------------------------------------------------------------


class TestCreateTask:
    def test_creates_with_working_status(self, engine):
        task = engine.create_task("test-agent")
        assert task.status == TaskStatus.WORKING

    def test_generates_uuid(self, engine):
        task = engine.create_task("test-agent")
        assert len(task.task_id) == 36  # UUID format

    def test_custom_task_id(self, engine):
        task = engine.create_task("test-agent", task_id="custom-id")
        assert task.task_id == "custom-id"

    def test_duplicate_id_rejected(self, engine):
        engine.create_task("test-agent", task_id="dup-id")
        with pytest.raises(ValueError, match="already exists"):
            engine.create_task("test-agent", task_id="dup-id")

    def test_stores_metadata(self, engine):
        task = engine.create_task("test-agent", model="gemini-3-pro", mode="read-only")
        assert task.agent == "test-agent"
        assert task.model == "gemini-3-pro"
        assert task.mode == "read-only"

    def test_default_mode(self, engine):
        task = engine.create_task("test-agent")
        assert task.mode == "read-write"

    def test_timestamps_set(self, engine):
        task = engine.create_task("test-agent")
        assert task.created_at > 0
        assert task.updated_at > 0
        assert task.created_at == task.updated_at

    def test_result_and_error_none(self, engine):
        task = engine.create_task("test-agent")
        assert task.result is None
        assert task.error is None


# ---------------------------------------------------------------------------
# TestGetTask
# ---------------------------------------------------------------------------


class TestGetTask:
    def test_get_existing_task(self, engine):
        task = engine.create_task("test-agent")
        found = engine.get_task(task.task_id)
        assert found is not None
        assert found.task_id == task.task_id

    def test_get_nonexistent_task(self, engine):
        assert engine.get_task("nonexistent") is None


# ---------------------------------------------------------------------------
# TestStateTransitions
# ---------------------------------------------------------------------------


class TestStateTransitions:
    def test_working_to_completed(self, engine):
        task = engine.create_task("test-agent")
        updated = engine.update_status(task.task_id, TaskStatus.COMPLETED)
        assert updated.status == TaskStatus.COMPLETED

    def test_working_to_failed(self, engine):
        task = engine.create_task("test-agent")
        updated = engine.update_status(task.task_id, TaskStatus.FAILED)
        assert updated.status == TaskStatus.FAILED

    def test_working_to_cancelled(self, engine):
        task = engine.create_task("test-agent")
        updated = engine.update_status(task.task_id, TaskStatus.CANCELLED)
        assert updated.status == TaskStatus.CANCELLED

    def test_working_to_input_required(self, engine):
        task = engine.create_task("test-agent")
        updated = engine.update_status(task.task_id, TaskStatus.INPUT_REQUIRED)
        assert updated.status == TaskStatus.INPUT_REQUIRED

    def test_input_required_to_working(self, engine):
        task = engine.create_task("test-agent")
        engine.update_status(task.task_id, TaskStatus.INPUT_REQUIRED)
        updated = engine.update_status(task.task_id, TaskStatus.WORKING)
        assert updated.status == TaskStatus.WORKING

    def test_input_required_to_completed(self, engine):
        task = engine.create_task("test-agent")
        engine.update_status(task.task_id, TaskStatus.INPUT_REQUIRED)
        updated = engine.update_status(task.task_id, TaskStatus.COMPLETED)
        assert updated.status == TaskStatus.COMPLETED

    def test_completed_to_working_rejected(self, engine):
        task = engine.create_task("test-agent")
        engine.update_status(task.task_id, TaskStatus.COMPLETED)
        with pytest.raises(InvalidTransitionError, match="completed.*working"):
            engine.update_status(task.task_id, TaskStatus.WORKING)

    def test_failed_to_working_rejected(self, engine):
        task = engine.create_task("test-agent")
        engine.update_status(task.task_id, TaskStatus.FAILED)
        with pytest.raises(InvalidTransitionError, match="failed.*working"):
            engine.update_status(task.task_id, TaskStatus.WORKING)

    def test_cancelled_to_working_rejected(self, engine):
        task = engine.create_task("test-agent")
        engine.cancel_task(task.task_id)
        with pytest.raises(InvalidTransitionError, match="cancelled.*working"):
            engine.update_status(task.task_id, TaskStatus.WORKING)

    def test_same_state_transition_allowed(self, engine):
        """Transitioning to the same state is a no-op, not an error."""
        task = engine.create_task("test-agent")
        updated = engine.update_status(task.task_id, TaskStatus.WORKING)
        assert updated.status == TaskStatus.WORKING

    def test_status_message_updated(self, engine):
        task = engine.create_task("test-agent")
        updated = engine.update_status(
            task.task_id, TaskStatus.WORKING, status_message="Processing..."
        )
        assert updated.status_message == "Processing..."

    def test_updated_at_changes(self, engine):
        task = engine.create_task("test-agent")
        original_updated = task.updated_at
        time.sleep(0.01)
        updated = engine.update_status(task.task_id, TaskStatus.COMPLETED)
        assert updated.updated_at > original_updated

    def test_nonexistent_task_raises(self, engine):
        with pytest.raises(TaskNotFoundError, match="not found"):
            engine.update_status("nonexistent", TaskStatus.COMPLETED)


# ---------------------------------------------------------------------------
# TestCompleteTask
# ---------------------------------------------------------------------------


class TestCompleteTask:
    def test_sets_status_and_result(self, engine):
        task = engine.create_task("test-agent")
        result = {"summary": "done", "artifacts": []}
        completed = engine.complete_task(task.task_id, result)
        assert completed.status == TaskStatus.COMPLETED
        assert completed.result == result

    def test_complete_from_input_required(self, engine):
        task = engine.create_task("test-agent")
        engine.update_status(task.task_id, TaskStatus.INPUT_REQUIRED)
        completed = engine.complete_task(task.task_id, {"ok": True})
        assert completed.status == TaskStatus.COMPLETED

    def test_complete_terminal_rejected(self, engine):
        task = engine.create_task("test-agent")
        engine.complete_task(task.task_id, {"ok": True})
        with pytest.raises(InvalidTransitionError):
            engine.complete_task(task.task_id, {"again": True})

    def test_complete_nonexistent_raises(self, engine):
        with pytest.raises(TaskNotFoundError):
            engine.complete_task("nonexistent", {"ok": True})


# ---------------------------------------------------------------------------
# TestFailTask
# ---------------------------------------------------------------------------


class TestFailTask:
    def test_sets_status_and_error(self, engine):
        task = engine.create_task("test-agent")
        failed = engine.fail_task(task.task_id, "Something went wrong")
        assert failed.status == TaskStatus.FAILED
        assert failed.error == "Something went wrong"

    def test_fail_terminal_rejected(self, engine):
        task = engine.create_task("test-agent")
        engine.fail_task(task.task_id, "first failure")
        with pytest.raises(InvalidTransitionError):
            engine.fail_task(task.task_id, "second failure")

    def test_fail_nonexistent_raises(self, engine):
        with pytest.raises(TaskNotFoundError):
            engine.fail_task("nonexistent", "error")


# ---------------------------------------------------------------------------
# TestCancelTask
# ---------------------------------------------------------------------------


class TestCancelTask:
    def test_cancel_working_task(self, engine):
        task = engine.create_task("test-agent")
        cancelled = engine.cancel_task(task.task_id)
        assert cancelled.status == TaskStatus.CANCELLED

    def test_cancel_input_required(self, engine):
        task = engine.create_task("test-agent")
        engine.update_status(task.task_id, TaskStatus.INPUT_REQUIRED)
        cancelled = engine.cancel_task(task.task_id)
        assert cancelled.status == TaskStatus.CANCELLED

    def test_cancel_completed_rejected(self, engine):
        task = engine.create_task("test-agent")
        engine.complete_task(task.task_id, {"ok": True})
        with pytest.raises(InvalidTransitionError):
            engine.cancel_task(task.task_id)


# ---------------------------------------------------------------------------
# TestListTasks
# ---------------------------------------------------------------------------


class TestListTasks:
    def test_empty_engine(self, engine):
        assert engine.list_tasks() == []

    def test_lists_all_tasks(self, engine):
        engine.create_task("agent-a")
        engine.create_task("agent-b")
        engine.create_task("agent-c")
        tasks = engine.list_tasks()
        assert len(tasks) == 3


# ---------------------------------------------------------------------------
# TestDeleteTask
# ---------------------------------------------------------------------------


class TestDeleteTask:
    def test_delete_existing(self, engine):
        task = engine.create_task("test-agent")
        assert engine.delete_task(task.task_id) is True
        assert engine.get_task(task.task_id) is None

    def test_delete_nonexistent(self, engine):
        assert engine.delete_task("nonexistent") is False


# ---------------------------------------------------------------------------
# TestTTLExpiry
# ---------------------------------------------------------------------------


class TestTTLExpiry:
    def test_terminal_task_expires(self, short_ttl_engine):
        task = short_ttl_engine.create_task("test-agent")
        short_ttl_engine.complete_task(task.task_id, {"ok": True})
        assert short_ttl_engine.get_task(task.task_id) is not None
        time.sleep(0.2)
        assert short_ttl_engine.get_task(task.task_id) is None

    def test_working_task_does_not_expire(self, short_ttl_engine):
        task = short_ttl_engine.create_task("test-agent")
        time.sleep(0.2)
        assert short_ttl_engine.get_task(task.task_id) is not None

    def test_failed_task_expires(self, short_ttl_engine):
        task = short_ttl_engine.create_task("test-agent")
        short_ttl_engine.fail_task(task.task_id, "error")
        time.sleep(0.2)
        assert short_ttl_engine.get_task(task.task_id) is None

    def test_cancelled_task_expires(self, short_ttl_engine):
        task = short_ttl_engine.create_task("test-agent")
        short_ttl_engine.cancel_task(task.task_id)
        time.sleep(0.2)
        assert short_ttl_engine.get_task(task.task_id) is None


# ---------------------------------------------------------------------------
# TestConcurrency
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_multiple_tasks_independent(self, engine):
        """Multiple tasks can be tracked independently."""
        t1 = engine.create_task("agent-a")
        t2 = engine.create_task("agent-b")
        t3 = engine.create_task("agent-c")

        engine.complete_task(t1.task_id, {"result": "a"})
        engine.fail_task(t2.task_id, "error-b")

        assert engine.get_task(t1.task_id).status == TaskStatus.COMPLETED
        assert engine.get_task(t2.task_id).status == TaskStatus.FAILED
        assert engine.get_task(t3.task_id).status == TaskStatus.WORKING


# ---------------------------------------------------------------------------
# TestWaitForUpdate
# ---------------------------------------------------------------------------


class TestWaitForUpdate:
    def test_wait_wakes_on_update(self, engine):
        """wait_for_update unblocks when status changes."""

        async def _test():
            task = engine.create_task("test-agent")

            async def updater():
                await asyncio.sleep(0.05)
                engine.complete_task(task.task_id, {"ok": True})

            asyncio.create_task(updater())
            await engine.wait_for_update(task.task_id, timeout=2.0)
            return engine.get_task(task.task_id)

        result = asyncio.run(_test())
        assert result.status == TaskStatus.COMPLETED

    def test_wait_timeout(self, engine):
        """wait_for_update raises TimeoutError when timeout expires."""

        async def _test():
            task = engine.create_task("test-agent")
            with pytest.raises(asyncio.TimeoutError):
                await engine.wait_for_update(task.task_id, timeout=0.05)

        asyncio.run(_test())

    def test_wait_nonexistent_raises(self, engine):
        """wait_for_update raises TaskNotFoundError for missing tasks."""

        async def _test():
            with pytest.raises(TaskNotFoundError):
                await engine.wait_for_update("nonexistent")

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# TestLockManager
# ---------------------------------------------------------------------------


class TestLockManager:
    """Tests for the advisory file lock manager."""

    def test_acquire_lock(self, lock_mgr):
        lock, warnings = lock_mgr.acquire_lock("t1", {".docs/plan.md"}, "read-only")
        assert lock.task_id == "t1"
        assert lock.paths == frozenset({".docs/plan.md"})
        assert lock.mode == "read-only"
        assert lock.acquired_at > 0
        assert warnings == []

    def test_release_lock(self, lock_mgr):
        lock_mgr.acquire_lock("t1", {".docs/plan.md"}, "read-only")
        assert lock_mgr.release_lock("t1") is True
        assert lock_mgr.get_lock("t1") is None

    def test_release_nonexistent_returns_false(self, lock_mgr):
        assert lock_mgr.release_lock("nonexistent") is False

    def test_double_acquire_rejected(self, lock_mgr):
        lock_mgr.acquire_lock("t1", {".docs/plan.md"}, "read-only")
        with pytest.raises(ValueError, match="already holds a lock"):
            lock_mgr.acquire_lock("t1", {".docs/other.md"}, "read-only")

    def test_conflict_detection_overlapping_paths(self, lock_mgr):
        lock_mgr.acquire_lock("t1", {".docs/plan.md", "src/main.rs"}, "read-write")
        _lock, warnings = lock_mgr.acquire_lock(
            "t2", {".docs/plan.md", "crates/foo.rs"}, "read-write"
        )
        assert len(warnings) == 1
        assert ".docs/plan.md" in warnings[0]
        assert "t1" in warnings[0]

    def test_no_conflict_disjoint_paths(self, lock_mgr):
        lock_mgr.acquire_lock("t1", {".docs/plan.md"}, "read-only")
        _lock, warnings = lock_mgr.acquire_lock("t2", {"src/main.rs"}, "read-write")
        assert warnings == []

    def test_check_conflicts(self, lock_mgr):
        lock_mgr.acquire_lock("t1", {".docs/plan.md"}, "read-only")
        conflicts = lock_mgr.check_conflicts({".docs/plan.md"})
        assert len(conflicts) == 1
        assert "t1" in conflicts[0]

    def test_check_conflicts_empty_when_no_overlap(self, lock_mgr):
        lock_mgr.acquire_lock("t1", {".docs/plan.md"}, "read-only")
        conflicts = lock_mgr.check_conflicts({"src/main.rs"})
        assert conflicts == []

    def test_get_lock_returns_specific_lock(self, lock_mgr):
        lock_mgr.acquire_lock("t1", {".docs/plan.md"}, "read-only")
        lock = lock_mgr.get_lock("t1")
        assert lock is not None
        assert lock.task_id == "t1"

    def test_get_lock_returns_none_for_missing(self, lock_mgr):
        assert lock_mgr.get_lock("nonexistent") is None

    def test_get_locks_returns_all(self, lock_mgr):
        lock_mgr.acquire_lock("t1", {".docs/a.md"}, "read-only")
        lock_mgr.acquire_lock("t2", {"src/b.rs"}, "read-write")
        locks = lock_mgr.get_locks()
        assert len(locks) == 2
        ids = {lock.task_id for lock in locks}
        assert ids == {"t1", "t2"}

    def test_get_locks_empty_initially(self, lock_mgr):
        assert lock_mgr.get_locks() == []

    def test_release_then_reacquire(self, lock_mgr):
        lock_mgr.acquire_lock("t1", {".docs/plan.md"}, "read-only")
        lock_mgr.release_lock("t1")
        lock, warnings = lock_mgr.acquire_lock("t1", {".docs/plan.md"}, "read-only")
        assert lock.task_id == "t1"
        assert warnings == []


# ---------------------------------------------------------------------------
# TestValidateReadonlyPaths
# ---------------------------------------------------------------------------


class TestValidateReadonlyPaths:
    """Tests for LockManager.validate_readonly_paths()."""

    def test_docs_path_allowed(self):
        violations = LockManager.validate_readonly_paths({".docs/plan.md"})
        assert violations == []

    def test_source_path_rejected(self):
        violations = LockManager.validate_readonly_paths({"src/main.rs"})
        assert violations == ["src/main.rs"]

    def test_mixed_paths(self):
        violations = LockManager.validate_readonly_paths(
            {".docs/plan.md", "src/main.rs", "crates/foo.rs"}
        )
        assert sorted(violations) == ["crates/foo.rs", "src/main.rs"]

    def test_empty_paths(self):
        violations = LockManager.validate_readonly_paths(set())
        assert violations == []

    def test_windows_backslash_normalized(self):
        violations = LockManager.validate_readonly_paths({".docs\\plan.md"})
        assert violations == []

    def test_nested_docs_path_allowed(self):
        violations = LockManager.validate_readonly_paths(
            {".docs/exec/2026-01-01-feature/step1.md"}
        )
        assert violations == []


# ---------------------------------------------------------------------------
# TestLockReleaseOnTerminalTransitions
# ---------------------------------------------------------------------------


class TestLockReleaseOnTerminalTransitions:
    """Tests that locks are released when tasks reach terminal states."""

    def test_lock_released_on_complete(self, engine_with_locks):
        engine, lm = engine_with_locks
        task = engine.create_task("test-agent")
        lm.acquire_lock(task.task_id, {".docs/plan.md"}, "read-only")
        assert lm.get_lock(task.task_id) is not None

        engine.complete_task(task.task_id, {"ok": True})
        assert lm.get_lock(task.task_id) is None

    def test_lock_released_on_fail(self, engine_with_locks):
        engine, lm = engine_with_locks
        task = engine.create_task("test-agent")
        lm.acquire_lock(task.task_id, {".docs/plan.md"}, "read-only")

        engine.fail_task(task.task_id, "error")
        assert lm.get_lock(task.task_id) is None

    def test_lock_released_on_cancel(self, engine_with_locks):
        engine, lm = engine_with_locks
        task = engine.create_task("test-agent")
        lm.acquire_lock(task.task_id, {".docs/plan.md"}, "read-only")

        engine.cancel_task(task.task_id)
        assert lm.get_lock(task.task_id) is None

    def test_lock_released_on_update_status_to_terminal(self, engine_with_locks):
        engine, lm = engine_with_locks
        task = engine.create_task("test-agent")
        lm.acquire_lock(task.task_id, {".docs/plan.md"}, "read-write")

        engine.update_status(task.task_id, TaskStatus.FAILED)
        assert lm.get_lock(task.task_id) is None

    def test_no_lock_leak_without_lock_acquired(self, engine_with_locks):
        """Completing a task without an acquired lock does not crash."""
        engine, lm = engine_with_locks
        task = engine.create_task("test-agent")
        # No lock acquired -- release should be a no-op
        engine.complete_task(task.task_id, {"ok": True})
        assert lm.get_locks() == []

    def test_lock_released_on_ttl_expiry(self, short_ttl_engine_with_locks):
        engine, lm = short_ttl_engine_with_locks
        task = engine.create_task("test-agent")
        lm.acquire_lock(task.task_id, {".docs/plan.md"}, "read-only")

        engine.complete_task(task.task_id, {"ok": True})
        # Lock already released by complete_task, but let's verify
        # the TTL expiry path also cleans up properly.
        assert lm.get_lock(task.task_id) is None
        time.sleep(0.2)
        assert engine.get_task(task.task_id) is None

    def test_engine_without_lock_manager_works(self):
        """TaskEngine without lock_manager still functions normally."""
        engine = TaskEngine(ttl_seconds=3600.0)
        task = engine.create_task("test-agent")
        engine.complete_task(task.task_id, {"ok": True})
        assert engine.get_task(task.task_id).status == TaskStatus.COMPLETED

    def test_same_state_working_does_not_release_lock(self, engine_with_locks):
        """Transitioning working -> working (no-op) does NOT release the lock."""
        engine, lm = engine_with_locks
        task = engine.create_task("test-agent")
        lm.acquire_lock(task.task_id, {".docs/plan.md"}, "read-only")

        engine.update_status(task.task_id, TaskStatus.WORKING)
        # Lock should still be held since working is not a terminal state.
        assert lm.get_lock(task.task_id) is not None

    def test_delete_task_does_not_release_lock(self, engine_with_locks):
        """delete_task is a hard removal and does NOT release the advisory lock."""
        engine, lm = engine_with_locks
        task = engine.create_task("test-agent")
        lm.acquire_lock(task.task_id, {".docs/plan.md"}, "read-only")

        engine.delete_task(task.task_id)
        # Lock should persist because delete_task is not a state transition.
        assert lm.get_lock(task.task_id) is not None

    def test_input_required_to_failed_releases_lock(self, engine_with_locks):
        """Transition from input_required to failed releases the advisory lock."""
        engine, lm = engine_with_locks
        task = engine.create_task("test-agent")
        lm.acquire_lock(task.task_id, {".docs/plan.md"}, "read-only")

        engine.update_status(task.task_id, TaskStatus.INPUT_REQUIRED)
        assert lm.get_lock(task.task_id) is not None

        engine.fail_task(task.task_id, "error while waiting for input")
        assert lm.get_lock(task.task_id) is None

    def test_input_required_to_cancelled_releases_lock(self, engine_with_locks):
        """Transition from input_required to cancelled releases the advisory lock."""
        engine, lm = engine_with_locks
        task = engine.create_task("test-agent")
        lm.acquire_lock(task.task_id, {".docs/plan.md"}, "read-only")

        engine.update_status(task.task_id, TaskStatus.INPUT_REQUIRED)
        assert lm.get_lock(task.task_id) is not None

        engine.cancel_task(task.task_id)
        assert lm.get_lock(task.task_id) is None

    def test_multiple_tasks_locks_independent(self, engine_with_locks):
        """Completing one task does not release another task's lock."""
        engine, lm = engine_with_locks
        t1 = engine.create_task("agent-a")
        t2 = engine.create_task("agent-b")
        lm.acquire_lock(t1.task_id, {".docs/a.md"}, "read-only")
        lm.acquire_lock(t2.task_id, {".docs/b.md"}, "read-only")

        engine.complete_task(t1.task_id, {"ok": True})
        assert lm.get_lock(t1.task_id) is None
        assert lm.get_lock(t2.task_id) is not None


# ---------------------------------------------------------------------------
# TestSessionIdStorage
# ---------------------------------------------------------------------------


class TestSessionIdStorage:
    """Tests for session_id storage on DispatchTask."""

    def test_session_id_none_by_default(self, engine):
        task = engine.create_task("test-agent")
        assert task.session_id is None

    def test_set_session_id(self, engine):
        task = engine.create_task("test-agent")
        engine.set_session_id(task.task_id, "ses-abc-123")
        updated = engine.get_task(task.task_id)
        assert updated.session_id == "ses-abc-123"

    def test_set_session_id_not_found(self, engine):
        with pytest.raises(TaskNotFoundError, match="not found"):
            engine.set_session_id("nonexistent-id", "ses-xyz")
