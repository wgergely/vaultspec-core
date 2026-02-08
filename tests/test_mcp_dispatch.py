from __future__ import annotations

from dispatch_server.server import (
    _extract_artifacts,
    _merge_artifacts,
    _resolve_effective_mode,
    _strip_quotes,
)

# ---------------------------------------------------------------------------
# TestHelpers (Extracted from server logic)
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_strip_quotes_normal(self):
        assert _strip_quotes('"hello"') == "hello"

    def test_strip_quotes_no_quotes(self):
        assert _strip_quotes("hello") == "hello"

    def test_strip_quotes_empty(self):
        assert _strip_quotes("") == ""

    def test_resolve_mode_explicit(self):
        assert _resolve_effective_mode("any", "read-only") == "read-only"

    def test_resolve_mode_default(self):
        # This test would normally look into _agent_cache,
        # but we are testing the logic flow here.
        assert _resolve_effective_mode("any", None) == "read-write"


# ---------------------------------------------------------------------------
# TestArtifactExtraction
# ---------------------------------------------------------------------------


class TestArtifactExtraction:
    def test_empty_text(self):
        assert _extract_artifacts("") == []

    def test_docs_paths(self):
        text = "I created .docs/plan/my-plan.md and .docs/adr/my-adr.md"
        result = _extract_artifacts(text)
        assert ".docs/adr/my-adr.md" in result
        assert ".docs/plan/my-plan.md" in result

    def test_src_paths(self):
        text = "Modified src/main.rs and src/lib.rs for the feature."
        result = _extract_artifacts(text)
        assert "src/main.rs" in result
        assert "src/lib.rs" in result

    def test_deduplication(self):
        text = "Modified src/main.rs then tested src/main.rs again."
        result = _extract_artifacts(text)
        assert result.count("src/main.rs") == 1

    def test_sorted_output(self):
        text = "Created src/z.rs then src/a.rs then .docs/b.md"
        result = _extract_artifacts(text)
        assert result == sorted(result)


# ---------------------------------------------------------------------------
# TestMergeArtifacts
# ---------------------------------------------------------------------------


class TestMergeArtifacts:
    def test_empty_both(self):
        assert _merge_artifacts([], []) == []

    def test_text_only(self):
        result = _merge_artifacts(["src/main.rs"], [])
        assert result == ["src/main.rs"]

    def test_written_only(self):
        result = _merge_artifacts([], [".docs/plan.md"])
        assert result == [".docs/plan.md"]

    def test_deduplication(self):
        result = _merge_artifacts(
            [".docs/plan.md", "src/main.rs"],
            [".docs/plan.md", "src/lib.rs"],
        )
        assert result.count(".docs/plan.md") == 1
        assert "src/main.rs" in result
        assert "src/lib.rs" in result


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
        lm.acquire_lock(task.task_id, {".docs/test.md"}, "read-only")

        assert task.task_id in lm._locks

        engine.complete_task(task.task_id, {"summary": "done"})

        assert task.task_id not in lm._locks
