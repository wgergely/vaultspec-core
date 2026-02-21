"""Integration tests for MCP subagent task engine.

Unit tests for helpers, artifact extraction, and merge have been moved to:
src/vaultspec/subagent_server/tests/test_helpers.py
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.api]


class TestTaskEngineIntegration:
    """Verify the task engine and lock manager interact correctly."""

    def test_task_completion_releases_lock(self):
        # We use the real components imported from subagent_server.server
        # but we should be careful about global state.
        # In a high-quality test, we'd inject a fresh engine.
        from vaultspec.orchestration import LockManager, TaskEngine

        lm = LockManager()
        engine = TaskEngine(lock_manager=lm)

        task = engine.create_task("test-agent")
        lm.acquire_lock(task.task_id, {".vault/test.md"}, "read-only")

        assert task.task_id in lm._locks

        engine.complete_task(task.task_id, {"summary": "done"})

        assert task.task_id not in lm._locks
