"""Integration tests for MCP dispatch task engine.

Unit tests for helpers, artifact extraction, and merge have been moved to:
.vaultspec/lib/src/dispatch_server/tests/test_helpers.py
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.api]

# ---------------------------------------------------------------------------
# TestTaskEngineIntegration
# ---------------------------------------------------------------------------


class TestTaskEngineIntegration:
    """Verify the task engine and lock manager interact correctly."""

    def test_task_completion_releases_lock(self):
        # We use the real components imported from dispatch_server.server
        # but we should be careful about global state.
        # In a high-quality test, we'd inject a fresh engine.
        from orchestration.task_engine import LockManager, TaskEngine

        lm = LockManager()
        engine = TaskEngine(lock_manager=lm)

        task = engine.create_task("test-agent")
        lm.acquire_lock(task.task_id, {".vault/test.md"}, "read-only")

        assert task.task_id in lm._locks

        engine.complete_task(task.task_id, {"summary": "done"})

        assert task.task_id not in lm._locks
