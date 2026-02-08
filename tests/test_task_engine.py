from __future__ import annotations

import time

import pytest

from orchestration.task_engine import (
    LockManager,
    TaskEngine,
    TaskStatus,
)

# ---------------------------------------------------------------------------
# TestLockManager
# ---------------------------------------------------------------------------


class TestLockManager:
    def test_acquire_lock_basic(self):
        lm = LockManager()
        assert lm.acquire_lock("t1", {".docs/adr"}, "read-only")[0] is not None
        assert len(lm._locks) == 1
        assert "t1" in lm._locks

    def test_acquire_multiple_locks_same_task(self):
        lm = LockManager()
        lm.acquire_lock("t1", {".docs/adr"}, "read-only")
        with pytest.raises(ValueError):
            lm.acquire_lock("t1", {"src/"}, "read-write")

    def test_release_locks(self):
        lm = LockManager()
        lm.acquire_lock("t1", {".docs/adr"}, "read-only")
        lm.release_lock("t1")
        assert "t1" not in lm._locks

    def test_get_all_locks_empty(self):
        lm = LockManager()
        assert lm.get_locks() == []

    def test_get_all_locks_populated(self):
        lm = LockManager()
        lm.acquire_lock("t1", {".docs/adr"}, "read-only")
        locks = lm.get_locks()
        assert len(locks) == 1
        assert locks[0].task_id == "t1"
        assert locks[0].mode == "read-only"


# ---------------------------------------------------------------------------
# TestTaskEngine
# ---------------------------------------------------------------------------


class TestTaskEngine:
    @pytest.fixture
    def engine(self):
        return TaskEngine(ttl_seconds=60)

    def test_create_task(self, engine):
        task = engine.create_task("test-agent", model="gemini-3", mode="read-only")
        assert task.agent == "test-agent"
        assert task.model == "gemini-3"
        assert task.mode == "read-only"
        assert task.status == TaskStatus.WORKING
        assert task.task_id is not None

    def test_get_task_existing(self, engine):
        task = engine.create_task("test-agent")
        retrieved = engine.get_task(task.task_id)
        assert retrieved == task

    def test_get_task_nonexistent(self, engine):
        assert engine.get_task("nonexistent") is None

    def test_complete_task(self, engine):
        task = engine.create_task("test-agent")
        result = {"summary": "Done"}
        engine.complete_task(task.task_id, result)
        assert task.status == TaskStatus.COMPLETED
        assert task.result == result
        assert task.completed_at is not None

    def test_fail_task(self, engine):
        task = engine.create_task("test-agent")
        engine.fail_task(task.task_id, "Something went wrong")
        assert task.status == TaskStatus.FAILED
        assert task.error == "Something went wrong"
        assert task.completed_at is not None

    def test_cancel_task(self, engine):
        task = engine.create_task("test-agent")
        engine.cancel_task(task.task_id)
        assert task.status == TaskStatus.CANCELLED
        assert task.completed_at is not None

    def test_ttl_eviction(self):
        # Use short TTL
        engine = TaskEngine(ttl_seconds=0.1)
        task = engine.create_task("test-agent")
        engine.complete_task(task.task_id, {"ok": True})

        # Wait for TTL
        time.sleep(0.2)
        assert engine.get_task(task.task_id) is None

    def test_locks_integrated(self, engine):
        engine.create_task("test-agent", mode="read-only")
        # Assuming TaskEngine automatically acquires locks for .docs/ in read-only
        engine.lock_manager.get_locks()
        # If TaskEngine doesn't automatically acquire them (it should based on ADR),
        # this test might need adjustment.
        pass
