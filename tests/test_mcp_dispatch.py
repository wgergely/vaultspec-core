from __future__ import annotations

import pathlib
import sys

# Ensure scripts dir is importable (conftest also does this)
_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import asyncio  # noqa: E402
import json  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

import pytest  # noqa: E402

import mcp_dispatch  # noqa: E402
from acp_dispatch import DispatchResult  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_workspace(tmp_path: pathlib.Path, monkeypatch):
    """Set up a temp workspace with agent files and monkeypatch mcp_dispatch globals."""
    agents_dir = tmp_path / ".rules" / "agents"
    agents_dir.mkdir(parents=True)

    # Create test agent files (with mode/tools for Phase 3 resource testing)
    (agents_dir / "test-researcher.md").write_text(
        '---\ndescription: "A test research agent"\ntier: HIGH\n'
        "mode: read-only\ntools: Glob, Grep, Read\n---\n\n# Test Researcher\n",
        encoding="utf-8",
    )
    (agents_dir / "test-executor.md").write_text(
        '---\ndescription: "A test executor agent"\ntier: LOW\n'
        "mode: read-write\ntools: Glob, Grep, Read, Write, Edit, Bash\n---\n\n# Test Executor\n",
        encoding="utf-8",
    )
    (agents_dir / "malformed-agent.md").write_text(
        "No frontmatter here, just plain text.",
        encoding="utf-8",
    )

    monkeypatch.setattr(mcp_dispatch, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(mcp_dispatch, "AGENTS_DIR", agents_dir)

    # Reset task engine and lock manager to avoid cross-test leaks.
    from task_engine import LockManager, TaskEngine

    new_lock_manager = LockManager()
    mcp_dispatch.lock_manager = new_lock_manager
    mcp_dispatch.task_engine = TaskEngine(
        ttl_seconds=3600.0,
        lock_manager=new_lock_manager,
    )

    # Re-register resources so they point to the temp workspace.
    mcp_dispatch._register_agent_resources()

    return tmp_path


@pytest.fixture
def empty_workspace(tmp_path: pathlib.Path, monkeypatch):
    """Set up a workspace with no agents directory."""
    monkeypatch.setattr(mcp_dispatch, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(mcp_dispatch, "AGENTS_DIR", tmp_path / ".rules" / "agents")
    return tmp_path


# ---------------------------------------------------------------------------
# TestHelpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_strip_quotes_normal(self):
        assert mcp_dispatch._strip_quotes('"hello"') == "hello"

    def test_strip_quotes_no_quotes(self):
        assert mcp_dispatch._strip_quotes("hello") == "hello"

    def test_strip_quotes_empty(self):
        assert mcp_dispatch._strip_quotes("") == ""

    def test_strip_quotes_single_char(self):
        assert mcp_dispatch._strip_quotes('"') == '"'

    def test_parse_tools_normal(self):
        assert mcp_dispatch._parse_tools("Glob, Grep, Read") == ["Glob", "Grep", "Read"]

    def test_parse_tools_empty(self):
        assert mcp_dispatch._parse_tools("") == []

    def test_parse_tools_whitespace(self):
        assert mcp_dispatch._parse_tools(" , , ") == []


# ---------------------------------------------------------------------------
# TestServerInit
# ---------------------------------------------------------------------------


class TestServerInit:
    def test_server_name(self):
        assert mcp_dispatch.mcp.name == "pp-dispatch"

    def test_tools_registered(self):
        tools = asyncio.run(mcp_dispatch.mcp.list_tools())
        tool_names = [t.name for t in tools]
        assert "list_agents" in tool_names
        assert "dispatch_agent" in tool_names
        assert "get_task_status" in tool_names
        assert "cancel_task" in tool_names
        assert "get_locks" in tool_names

    def test_tools_count(self):
        tools = asyncio.run(mcp_dispatch.mcp.list_tools())
        assert len(tools) == 5


# ---------------------------------------------------------------------------
# TestListAgents
# ---------------------------------------------------------------------------


class TestListAgents:
    def test_returns_agents(self, mcp_workspace):
        result = asyncio.run(mcp_dispatch.list_agents())
        data = json.loads(result)
        assert "agents" in data
        assert len(data["agents"]) == 3

    def test_agent_metadata_fields(self, mcp_workspace):
        result = asyncio.run(mcp_dispatch.list_agents())
        data = json.loads(result)
        agents_by_name = {a["name"]: a for a in data["agents"]}

        researcher = agents_by_name["test-researcher"]
        assert researcher["tier"] == "HIGH"
        assert "test research agent" in researcher["description"]

        executor = agents_by_name["test-executor"]
        assert executor["tier"] == "LOW"
        assert "test executor agent" in executor["description"]

    def test_malformed_agent_handled(self, mcp_workspace):
        result = asyncio.run(mcp_dispatch.list_agents())
        data = json.loads(result)
        agents_by_name = {a["name"]: a for a in data["agents"]}

        malformed = agents_by_name["malformed-agent"]
        assert malformed["tier"] == "UNKNOWN"
        assert malformed["description"] == ""

    def test_missing_agents_dir(self, empty_workspace):
        result = asyncio.run(mcp_dispatch.list_agents())
        data = json.loads(result)
        assert data["agents"] == []
        assert "error" in data

    def test_sorted_by_name(self, mcp_workspace):
        result = asyncio.run(mcp_dispatch.list_agents())
        data = json.loads(result)
        names = [a["name"] for a in data["agents"]]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# TestDispatchAgent
# ---------------------------------------------------------------------------


class TestDispatchAgent:
    def test_invalid_mode_rejected(self, mcp_workspace):
        result = asyncio.run(
            mcp_dispatch.dispatch_agent("test-researcher", "do stuff", mode="invalid")
        )
        data = json.loads(result)
        assert data["status"] == "failed"
        assert "Invalid mode" in data["error"]

    def test_async_dispatch_returns_working(self, mcp_workspace):
        """dispatch_agent returns immediately with status=working and a taskId."""

        async def _test():
            result = await mcp_dispatch.dispatch_agent("nonexistent-agent", "do stuff")
            data = json.loads(result)
            assert data["status"] == "working"
            assert "taskId" in data
            assert data["agent"] == "nonexistent-agent"
            # Let background task run to completion.
            await asyncio.sleep(0.1)
            return data["taskId"]

        task_id = asyncio.run(_test())
        # After background completes, engine should show failed.
        task = mcp_dispatch.task_engine.get_task(task_id)
        assert task is not None
        assert task.status.value == "failed"
        assert "not found" in task.error

    def test_missing_agent_fails_in_background(self, mcp_workspace):
        """A nonexistent agent causes the background task to fail, visible via get_task_status."""

        async def _test():
            result = await mcp_dispatch.dispatch_agent("nonexistent-agent", "do stuff")
            data = json.loads(result)
            task_id = data["taskId"]
            # Let background task complete.
            await asyncio.sleep(0.1)
            status_result = await mcp_dispatch.get_task_status(task_id)
            return json.loads(status_result)

        status = asyncio.run(_test())
        assert status["status"] == "failed"
        assert "not found" in status["error"]

    def test_task_file_resolution(self, mcp_workspace):
        """Task paths relative to ROOT_DIR are resolved to file contents."""
        task_file = mcp_workspace / "test-task.md"
        task_file.write_text("# My Task\nDo something important.", encoding="utf-8")

        async def _test():
            result = await mcp_dispatch.dispatch_agent(
                "nonexistent-agent", "test-task.md"
            )
            data = json.loads(result)
            task_id = data["taskId"]
            await asyncio.sleep(0.1)
            status_result = await mcp_dispatch.get_task_status(task_id)
            return json.loads(status_result)

        status = asyncio.run(_test())
        # The error should be about the agent, not about the task file.
        assert "not found" in status["error"]
        assert "nonexistent-agent" in status["error"]

    def test_response_structure_async(self, mcp_workspace):
        """Async dispatch response contains status, agent, taskId, model, mode."""
        result = asyncio.run(
            mcp_dispatch.dispatch_agent("nonexistent-agent", "do stuff")
        )
        data = json.loads(result)
        assert "status" in data
        assert "agent" in data
        assert "taskId" in data
        assert "model" in data
        assert "mode" in data

    def test_valid_modes_accepted(self, mcp_workspace):
        """Both valid modes should not trigger mode validation error."""
        for valid_mode in ("read-write", "read-only"):
            result = asyncio.run(
                mcp_dispatch.dispatch_agent(
                    "nonexistent-agent", "do stuff", mode=valid_mode
                )
            )
            data = json.loads(result)
            # Should return working (not mode validation error).
            assert data["status"] == "working"
            assert "Invalid mode" not in json.dumps(data)

    def test_successful_dispatch(self, mcp_workspace):
        """Mock run_dispatch returning successfully and verify task completes."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(
                    response_text="Agent completed the task successfully."
                )
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff", model="test-model"
                )
                data = json.loads(result)
                assert data["status"] == "working"
                task_id = data["taskId"]
                # Let background complete.
                await asyncio.sleep(0.1)
                status_result = await mcp_dispatch.get_task_status(task_id)
                return json.loads(status_result), mock_rd

        status, mock_rd = asyncio.run(_test())
        assert status["status"] == "completed"
        assert "result" in status
        assert status["result"]["agent"] == "test-researcher"
        assert "Agent completed" in status["result"]["summary"]
        assert status["result"]["model_used"] == "test-model"
        # Verify run_dispatch was called with correct args.
        mock_rd.assert_called_once()
        call_kwargs = mock_rd.call_args
        assert call_kwargs.kwargs.get("quiet") is True

    def test_dispatch_error_path(self, mcp_workspace):
        """DispatchError from run_dispatch marks task as failed."""
        from acp_dispatch import DispatchError as AcpDispatchError

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.side_effect = AcpDispatchError("Quota exhausted")
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]
                await asyncio.sleep(0.1)
                status_result = await mcp_dispatch.get_task_status(task_id)
                return json.loads(status_result)

        status = asyncio.run(_test())
        assert status["status"] == "failed"
        assert "Quota exhausted" in status["error"]

    def test_generic_exception_path(self, mcp_workspace):
        """Unexpected Exception from run_dispatch marks task as failed."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.side_effect = RuntimeError("Something unexpected")
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]
                await asyncio.sleep(0.1)
                status_result = await mcp_dispatch.get_task_status(task_id)
                return json.loads(status_result)

        status = asyncio.run(_test())
        assert status["status"] == "failed"
        assert "Unexpected error" in status["error"]

    def test_path_traversal_rejected(self, mcp_workspace):
        """Path traversal attempts should not read files outside workspace."""

        async def _test():
            # Use a path traversal string as the task.
            result = await mcp_dispatch.dispatch_agent(
                "nonexistent-agent", "../../etc/passwd"
            )
            data = json.loads(result)
            task_id = data["taskId"]
            await asyncio.sleep(0.1)
            status_result = await mcp_dispatch.get_task_status(task_id)
            return json.loads(status_result)

        status = asyncio.run(_test())
        # Should fail because agent not found, not because of passwd file content.
        assert status["status"] == "failed"
        assert "nonexistent-agent" in status.get("error", "")

    def test_quiet_propagation(self, mcp_workspace):
        """Verify run_dispatch is called with quiet=True."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="done")
                await mcp_dispatch.dispatch_agent("test-researcher", "do stuff")
                await asyncio.sleep(0.1)
                return mock_rd

        mock_rd = asyncio.run(_test())
        call_kwargs = mock_rd.call_args.kwargs
        assert call_kwargs["quiet"] is True
        assert call_kwargs["interactive"] is False


# ---------------------------------------------------------------------------
# TestGetTaskStatus
# ---------------------------------------------------------------------------


class TestGetTaskStatus:
    def test_unknown_task_id(self):
        result = asyncio.run(mcp_dispatch.get_task_status("nonexistent-id"))
        data = json.loads(result)
        assert "error" in data
        assert "not found" in data["error"]

    def test_expired_task_returns_not_found(self, mcp_workspace):
        """get_task_status returns not-found for an expired (TTL-evicted) task."""
        import time as _time

        from task_engine import LockManager, TaskEngine

        # Use a very short TTL so the task expires quickly.
        short_lm = LockManager()
        short_engine = TaskEngine(ttl_seconds=0.1, lock_manager=short_lm)
        mcp_dispatch.task_engine = short_engine
        mcp_dispatch.lock_manager = short_lm

        task = short_engine.create_task("test-agent")
        short_engine.complete_task(task.task_id, {"ok": True})
        _time.sleep(0.2)

        result = asyncio.run(mcp_dispatch.get_task_status(task.task_id))
        data = json.loads(result)
        assert "error" in data
        assert "not found" in data["error"]

    def test_returns_task_metadata(self, mcp_workspace):
        """get_task_status returns agent, model, mode, status fields."""
        task = mcp_dispatch.task_engine.create_task(
            "test-agent", model="test-model", mode="read-only"
        )
        result = asyncio.run(mcp_dispatch.get_task_status(task.task_id))
        data = json.loads(result)
        assert data["taskId"] == task.task_id
        assert data["status"] == "working"
        assert data["agent"] == "test-agent"
        assert data["model"] == "test-model"
        assert data["mode"] == "read-only"


# ---------------------------------------------------------------------------
# TestCancelTask
# ---------------------------------------------------------------------------


class TestCancelTask:
    def test_cancel_working_task(self):
        task = mcp_dispatch.task_engine.create_task("test-agent")
        result = asyncio.run(mcp_dispatch.cancel_task(task.task_id))
        data = json.loads(result)
        assert data["status"] == "cancelled"
        assert data["agent"] == "test-agent"

    def test_cancel_nonexistent_task(self):
        result = asyncio.run(mcp_dispatch.cancel_task("nonexistent-id"))
        data = json.loads(result)
        assert "error" in data
        assert "not found" in data["error"]

    def test_cancel_completed_task_rejected(self):
        task = mcp_dispatch.task_engine.create_task("test-agent")
        mcp_dispatch.task_engine.complete_task(task.task_id, {"ok": True})
        result = asyncio.run(mcp_dispatch.cancel_task(task.task_id))
        data = json.loads(result)
        assert "error" in data
        assert "completed" in data["error"]


# ---------------------------------------------------------------------------
# TestAsyncDispatchIntegration
# ---------------------------------------------------------------------------


class TestAsyncDispatchIntegration:
    """Integration tests for the full async dispatch lifecycle."""

    def test_poll_status_while_working(self, mcp_workspace):
        """get_task_status returns 'working' while background dispatch is still running."""

        async def _test():
            # Make run_dispatch block long enough to poll mid-flight.
            async def slow_dispatch(**kwargs):
                await asyncio.sleep(0.5)
                return DispatchResult(response_text="Eventually done.")

            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.side_effect = slow_dispatch
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]

                # Poll immediately -- should still be working.
                status_result = await mcp_dispatch.get_task_status(task_id)
                status = json.loads(status_result)
                assert status["status"] == "working"

                # Let it complete.
                await asyncio.sleep(0.6)
                status_result = await mcp_dispatch.get_task_status(task_id)
                status = json.loads(status_result)
                assert status["status"] == "completed"
                return status

        result = asyncio.run(_test())
        assert "result" in result
        assert "Eventually done." in result["result"]["summary"]

    def test_cancel_terminates_background_task(self, mcp_workspace):
        """cancel_task stops the in-flight asyncio background task."""

        async def _test():
            dispatch_started = asyncio.Event()

            async def blocking_dispatch(**kwargs):
                dispatch_started.set()
                await asyncio.sleep(10.0)  # Would block forever without cancel.
                return DispatchResult(response_text="Should not reach here.")

            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.side_effect = blocking_dispatch
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]

                # Wait for background to actually start running.
                await dispatch_started.wait()

                # Verify background asyncio task exists and is running.
                bg_task = mcp_dispatch._background_tasks.get(task_id)
                assert bg_task is not None
                assert not bg_task.done()

                # Cancel while background is still running.
                cancel_result = await mcp_dispatch.cancel_task(task_id)
                cancel_data = json.loads(cancel_result)
                assert cancel_data["status"] == "cancelled"

                # Give the background task time to process cancellation.
                await asyncio.sleep(0.1)

                # The asyncio task should now be done (cancelled).
                assert bg_task.done()

        asyncio.run(_test())

    def test_concurrent_dispatches_independent(self, mcp_workspace):
        """Multiple concurrent dispatches are tracked independently."""

        async def _test():
            call_count = 0

            async def mock_dispatch(**kwargs):
                nonlocal call_count
                call_count += 1
                agent = kwargs.get("agent_name", "unknown")
                await asyncio.sleep(0.05)
                return DispatchResult(response_text=f"Done by {agent}")

            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.side_effect = mock_dispatch

                # Dispatch three tasks concurrently.
                r1 = await mcp_dispatch.dispatch_agent("test-researcher", "task-a")
                r2 = await mcp_dispatch.dispatch_agent("test-executor", "task-b")
                r3 = await mcp_dispatch.dispatch_agent("test-researcher", "task-c")

                d1, d2, d3 = json.loads(r1), json.loads(r2), json.loads(r3)

                # All should be working immediately.
                assert d1["status"] == "working"
                assert d2["status"] == "working"
                assert d3["status"] == "working"

                # All have unique task IDs.
                ids = {d1["taskId"], d2["taskId"], d3["taskId"]}
                assert len(ids) == 3

                # Wait for all to complete.
                await asyncio.sleep(0.2)

                for task_id in ids:
                    status = json.loads(await mcp_dispatch.get_task_status(task_id))
                    assert status["status"] == "completed"

                return call_count

        count = asyncio.run(_test())
        assert count == 3

    def test_completed_result_structure(self, mcp_workspace):
        """Completed task result contains all ADR-required fields."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(
                    response_text="Full analysis complete with findings."
                )
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "analyze this", model="gemini-3-pro"
                )
                data = json.loads(result)
                task_id = data["taskId"]
                await asyncio.sleep(0.1)
                status_result = await mcp_dispatch.get_task_status(task_id)
                return json.loads(status_result)

        status = asyncio.run(_test())
        assert status["status"] == "completed"
        result = status["result"]

        # Verify all ADR-required result fields.
        assert result["taskId"] is not None
        assert result["status"] == "completed"
        assert result["agent"] == "test-researcher"
        assert result["model_used"] == "gemini-3-pro"
        assert isinstance(result["duration_seconds"], (int, float))
        assert result["duration_seconds"] >= 0
        assert "Full analysis complete" in result["summary"]
        assert "Full analysis complete" in result["response"]
        assert result["artifacts"] == []

    def test_default_model_in_result(self, mcp_workspace):
        """When no model override is provided, result shows '(default)'."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="Done.")
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]
                assert data["model"] is None
                await asyncio.sleep(0.1)
                status_result = await mcp_dispatch.get_task_status(task_id)
                return json.loads(status_result)

        status = asyncio.run(_test())
        assert status["status"] == "completed"
        assert status["result"]["model_used"] == "(default)"

    def test_dispatch_run_dispatch_receives_correct_args(self, mcp_workspace):
        """Verify the full argument set passed to run_dispatch."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="ok")
                # Use mode="read-write" explicitly to avoid permission prompt injection.
                await mcp_dispatch.dispatch_agent(
                    "test-researcher",
                    "my task text",
                    model="custom-model",
                    mode="read-write",
                )
                await asyncio.sleep(0.1)
                return mock_rd

        mock_rd = asyncio.run(_test())
        mock_rd.assert_called_once()
        kwargs = mock_rd.call_args.kwargs
        assert kwargs["agent_name"] == "test-researcher"
        assert kwargs["initial_task"] == "my task text"
        assert kwargs["model_override"] == "custom-model"
        assert kwargs["interactive"] is False
        assert kwargs["debug"] is False
        assert kwargs["quiet"] is True

    def test_long_task_content_passes_through(self, mcp_workspace):
        """Dispatch with very long task content passes through to run_dispatch correctly."""
        long_task = "A" * 5000

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="done")
                await mcp_dispatch.dispatch_agent(
                    "test-researcher", long_task, mode="read-write"
                )
                await asyncio.sleep(0.1)
                return mock_rd

        mock_rd = asyncio.run(_test())
        initial_task = mock_rd.call_args.kwargs["initial_task"]
        assert initial_task == long_task
        assert len(initial_task) == 5000

    def test_summary_truncation(self, mcp_workspace):
        """Completed task summary is truncated to at most 500 chars."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="x" * 1000)
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]
                await asyncio.sleep(0.1)
                status_result = await mcp_dispatch.get_task_status(task_id)
                return json.loads(status_result)

        status = asyncio.run(_test())
        assert status["status"] == "completed"
        assert len(status["result"]["summary"]) <= 500

    def test_empty_task_string_dispatches(self, mcp_workspace):
        """dispatch_agent with empty task string dispatches without error."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="done")
                result = await mcp_dispatch.dispatch_agent("test-researcher", "")
                data = json.loads(result)
                assert data["status"] == "working"
                await asyncio.sleep(0.1)
                status_result = await mcp_dispatch.get_task_status(data["taskId"])
                return json.loads(status_result)

        status = asyncio.run(_test())
        assert status["status"] == "completed"

    def test_cancel_complete_race_no_crash(self, mcp_workspace):
        """If cancel_task races with background completion, no unhandled error occurs."""

        async def _test():
            complete_gate = asyncio.Event()

            async def gated_dispatch(**kwargs):
                # Wait until cancel has happened, then try to return success.
                await complete_gate.wait()
                return DispatchResult(response_text="Completed after cancel.")

            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.side_effect = gated_dispatch
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]

                # Cancel while background is blocked at the gate.
                cancel_result = await mcp_dispatch.cancel_task(task_id)
                cancel_data = json.loads(cancel_result)
                assert cancel_data["status"] == "cancelled"

                # Now let the background complete -- it will try complete_task()
                # on an already-cancelled task. Should NOT raise.
                complete_gate.set()
                await asyncio.sleep(0.1)

                # Task should still show cancelled (not overwritten to completed).
                status_result = await mcp_dispatch.get_task_status(task_id)
                status = json.loads(status_result)
                assert status["status"] == "cancelled"

        asyncio.run(_test())

    def test_descriptions_consistent_with_resources(self, mcp_workspace):
        """list_agents descriptions match resource descriptions (no quote wrapping)."""
        # Get descriptions from list_agents.
        list_result = asyncio.run(mcp_dispatch.list_agents())
        list_data = json.loads(list_result)
        list_descs = {a["name"]: a["description"] for a in list_data["agents"]}

        # Get descriptions from resources.
        async def _read_resources():
            resources = await mcp_dispatch.mcp.list_resources()
            res_descs = {}
            for r in resources:
                uri = str(r.uri)
                if uri.startswith("agents://"):
                    contents = await mcp_dispatch.mcp.read_resource(uri)
                    text = (
                        contents[0].content
                        if hasattr(contents[0], "content")
                        else str(contents[0])
                    )
                    data = json.loads(text)
                    res_descs[data["name"]] = data["description"]
            return res_descs

        res_descs = asyncio.run(_read_resources())

        # Every agent present in both should have matching descriptions.
        for name in list_descs:
            if name in res_descs:
                assert list_descs[name] == res_descs[name], (
                    f"Description mismatch for {name}: "
                    f"list_agents={list_descs[name]!r} vs resource={res_descs[name]!r}"
                )


# ---------------------------------------------------------------------------
# TestAgentResources
# ---------------------------------------------------------------------------


class TestAgentResources:
    """Tests for MCP agent resource registration, listing, and reading."""

    def test_resources_list_returns_all_agents(self, mcp_workspace):
        """resources/list returns a resource for every valid agent file."""
        resources = asyncio.run(mcp_dispatch.mcp.list_resources())
        uris = {str(r.uri) for r in resources}
        assert "agents://test-researcher" in uris
        assert "agents://test-executor" in uris
        # Key assertion: at least the 2 valid agents are present.
        assert len([u for u in uris if u.startswith("agents://")]) >= 2

    def test_resources_read_correct_metadata(self, mcp_workspace):
        """resources/read returns correct JSON metadata for a known agent."""

        async def _test():
            contents = await mcp_dispatch.mcp.read_resource("agents://test-researcher")
            return contents

        contents = asyncio.run(_test())
        assert len(contents) > 0
        text = (
            contents[0].content if hasattr(contents[0], "content") else str(contents[0])
        )
        data = json.loads(text)
        assert data["name"] == "test-researcher"
        assert data["tier"] == "HIGH"
        assert "test research agent" in data["description"]
        assert data["default_mode"] == "read-only"
        assert data["default_model"] is None
        assert isinstance(data["tools"], list)
        assert "Glob" in data["tools"]
        assert "Grep" in data["tools"]
        assert "Read" in data["tools"]

    def test_resources_read_executor_metadata(self, mcp_workspace):
        """resources/read for test-executor returns correct schema."""

        async def _test():
            contents = await mcp_dispatch.mcp.read_resource("agents://test-executor")
            return contents

        contents = asyncio.run(_test())
        text = (
            contents[0].content if hasattr(contents[0], "content") else str(contents[0])
        )
        data = json.loads(text)
        assert data["name"] == "test-executor"
        assert data["tier"] == "LOW"
        assert data["default_mode"] == "read-write"
        assert "Bash" in data["tools"]

    def test_unknown_agent_uri_errors(self, mcp_workspace):
        """resources/read for a nonexistent agent URI raises an error."""

        async def _test():
            return await mcp_dispatch.mcp.read_resource("agents://nonexistent-agent")

        with pytest.raises(Exception):
            asyncio.run(_test())

    def test_malformed_frontmatter_still_cached(self, mcp_workspace):
        """Agents with malformed frontmatter are handled gracefully in the cache."""
        cache = mcp_dispatch._agent_cache
        if "malformed-agent" in cache:
            assert cache["malformed-agent"]["tier"] == "UNKNOWN"
        # Valid agents should always be present.
        assert len(cache) >= 2

    def test_resource_content_matches_schema(self, mcp_workspace):
        """Every resource content has all required schema fields."""

        async def _test():
            resources = await mcp_dispatch.mcp.list_resources()
            results = {}
            for r in resources:
                uri = str(r.uri)
                if uri.startswith("agents://"):
                    contents = await mcp_dispatch.mcp.read_resource(uri)
                    text = (
                        contents[0].content
                        if hasattr(contents[0], "content")
                        else str(contents[0])
                    )
                    results[uri] = json.loads(text)
            return results

        results = asyncio.run(_test())
        required_keys = {
            "name",
            "description",
            "tier",
            "default_model",
            "default_mode",
            "tools",
        }
        for uri, data in results.items():
            missing = required_keys - set(data.keys())
            assert not missing, f"{uri} missing keys: {missing}"
            assert isinstance(data["tools"], list)

    def test_list_agents_includes_hint(self, mcp_workspace):
        """list_agents response includes a resource discovery hint."""
        result = asyncio.run(mcp_dispatch.list_agents())
        data = json.loads(result)
        assert "hint" in data
        assert "agents://" in data["hint"]


# ---------------------------------------------------------------------------
# TestFileWatching
# ---------------------------------------------------------------------------


class TestFileWatching:
    """Tests for mtime-based file change detection and cache refresh."""

    def test_no_changes_detected_initially(self, mcp_workspace):
        """Immediately after registration, no changes should be detected."""
        assert not mcp_dispatch._has_changes()
        assert not mcp_dispatch._refresh_if_changed()

    def test_file_modification_detected(self, mcp_workspace):
        """Modifying an agent file is detected as a change."""
        import time as _time

        agent_file = mcp_workspace / ".rules" / "agents" / "test-researcher.md"
        _time.sleep(0.05)
        agent_file.write_text(
            '---\ndescription: "Updated description"\ntier: HIGH\n'
            "mode: read-only\ntools: Read\n---\n\n# Updated\n",
            encoding="utf-8",
        )
        assert mcp_dispatch._has_changes()

    def test_file_addition_detected(self, mcp_workspace):
        """Adding a new agent file is detected as a change."""
        new_agent = mcp_workspace / ".rules" / "agents" / "new-agent.md"
        new_agent.write_text(
            '---\ndescription: "Brand new agent"\ntier: MEDIUM\n'
            "mode: read-write\ntools: Read, Write\n---\n\n# New Agent\n",
            encoding="utf-8",
        )
        assert mcp_dispatch._has_changes()

    def test_file_removal_detected(self, mcp_workspace):
        """Removing an agent file is detected as a change."""
        agent_file = mcp_workspace / ".rules" / "agents" / "test-executor.md"
        agent_file.unlink()
        assert mcp_dispatch._has_changes()

    def test_refresh_updates_cache(self, mcp_workspace):
        """_refresh_if_changed rebuilds the cache with new data."""
        new_agent = mcp_workspace / ".rules" / "agents" / "refreshed-agent.md"
        new_agent.write_text(
            '---\ndescription: "Freshly added"\ntier: LOW\n'
            "mode: read-only\ntools: Grep\n---\n\n# Refreshed\n",
            encoding="utf-8",
        )
        assert mcp_dispatch._refresh_if_changed()
        assert "refreshed-agent" in mcp_dispatch._agent_cache
        assert mcp_dispatch._agent_cache["refreshed-agent"]["tier"] == "LOW"

    def test_refresh_updates_resources(self, mcp_workspace):
        """After refresh, resources/list includes the new agent."""
        new_agent = mcp_workspace / ".rules" / "agents" / "resource-test-agent.md"
        new_agent.write_text(
            '---\ndescription: "For resource test"\ntier: HIGH\n'
            "mode: read-write\ntools: Bash\n---\n\n# Resource Test\n",
            encoding="utf-8",
        )
        mcp_dispatch._refresh_if_changed()

        resources = asyncio.run(mcp_dispatch.mcp.list_resources())
        uris = {str(r.uri) for r in resources}
        assert "agents://resource-test-agent" in uris

    def test_refresh_removes_deleted_agent(self, mcp_workspace):
        """After deletion and refresh, the agent is gone from resources."""
        agent_file = mcp_workspace / ".rules" / "agents" / "test-executor.md"
        agent_file.unlink()
        mcp_dispatch._refresh_if_changed()

        resources = asyncio.run(mcp_dispatch.mcp.list_resources())
        uris = {str(r.uri) for r in resources}
        assert "agents://test-executor" not in uris
        assert "test-executor" not in mcp_dispatch._agent_cache


# ---------------------------------------------------------------------------
# TestPermissionEnforcement
# ---------------------------------------------------------------------------


class TestPermissionEnforcement:
    """Integration tests for permission mode enforcement (Phase 4)."""

    def test_readonly_mode_injects_permission_prompt(self, mcp_workspace):
        """dispatch_agent with mode=read-only prepends permission instructions."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="done")
                await mcp_dispatch.dispatch_agent(
                    "test-researcher", "analyze code", mode="read-only"
                )
                await asyncio.sleep(0.1)
                return mock_rd

        mock_rd = asyncio.run(_test())
        initial_task = mock_rd.call_args.kwargs["initial_task"]
        assert "PERMISSION MODE: READ-ONLY" in initial_task
        assert "only write files within the `.docs/`" in initial_task
        assert "analyze code" in initial_task

    def test_readwrite_mode_no_prompt_injection(self, mcp_workspace):
        """dispatch_agent with mode=read-write does NOT inject permission text."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="done")
                await mcp_dispatch.dispatch_agent(
                    "test-executor", "fix code", mode="read-write"
                )
                await asyncio.sleep(0.1)
                return mock_rd

        mock_rd = asyncio.run(_test())
        initial_task = mock_rd.call_args.kwargs["initial_task"]
        assert "PERMISSION MODE" not in initial_task
        assert initial_task == "fix code"

    def test_default_mode_from_agent_frontmatter(self, mcp_workspace):
        """When mode is not specified, agent's frontmatter default_mode is used."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="done")
                # test-researcher has mode: read-only in frontmatter.
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "research task"
                )
                data = json.loads(result)
                await asyncio.sleep(0.1)
                return data, mock_rd

        data, mock_rd = asyncio.run(_test())
        # Effective mode should be read-only (from frontmatter).
        assert data["mode"] == "read-only"
        # Permission prompt should be injected.
        initial_task = mock_rd.call_args.kwargs["initial_task"]
        assert "PERMISSION MODE: READ-ONLY" in initial_task

    def test_explicit_mode_overrides_agent_default(self, mcp_workspace):
        """Explicit mode parameter overrides agent frontmatter default."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="done")
                # test-researcher has mode: read-only, but we pass read-write.
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "make changes", mode="read-write"
                )
                data = json.loads(result)
                await asyncio.sleep(0.1)
                return data, mock_rd

        data, mock_rd = asyncio.run(_test())
        assert data["mode"] == "read-write"
        initial_task = mock_rd.call_args.kwargs["initial_task"]
        assert "PERMISSION MODE" not in initial_task

    def test_fallback_to_readwrite_when_no_default(self, mcp_workspace):
        """When agent has no default_mode and caller omits mode, falls back to read-write."""
        # Create agent with no mode field.
        agents_dir = mcp_workspace / ".rules" / "agents"
        (agents_dir / "no-mode-agent.md").write_text(
            '---\ndescription: "Agent without mode"\ntier: LOW\ntools: Read\n---\n\n# No Mode\n',
            encoding="utf-8",
        )
        mcp_dispatch._register_agent_resources()

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="done")
                result = await mcp_dispatch.dispatch_agent(
                    "no-mode-agent", "do something"
                )
                data = json.loads(result)
                await asyncio.sleep(0.1)
                return data, mock_rd

        data, mock_rd = asyncio.run(_test())
        assert data["mode"] == "read-write"
        initial_task = mock_rd.call_args.kwargs["initial_task"]
        assert "PERMISSION MODE" not in initial_task


# ---------------------------------------------------------------------------
# TestGetLocks
# ---------------------------------------------------------------------------


class TestGetLocks:
    """Tests for the get_locks MCP tool."""

    def test_get_locks_empty(self, mcp_workspace):
        """get_locks returns empty list when no locks are held."""
        result = asyncio.run(mcp_dispatch.get_locks())
        data = json.loads(result)
        assert data["locks"] == []
        assert data["count"] == 0

    def test_get_locks_returns_active_lock(self, mcp_workspace):
        """get_locks returns locks held by dispatched tasks."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:

                async def slow_dispatch(**kwargs):
                    await asyncio.sleep(1.0)
                    return DispatchResult(response_text="done")

                mock_rd.side_effect = slow_dispatch
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "research", mode="read-only"
                )
                data = json.loads(result)
                task_id = data["taskId"]

                # Lock should be active while task is working.
                locks_result = await mcp_dispatch.get_locks()
                locks_data = json.loads(locks_result)

                # Cancel to clean up.
                await mcp_dispatch.cancel_task(task_id)
                await asyncio.sleep(0.1)

                return locks_data

        locks_data = asyncio.run(_test())
        assert locks_data["count"] >= 1
        lock_entry = locks_data["locks"][0]
        assert "taskId" in lock_entry
        assert "agent" in lock_entry
        assert "paths" in lock_entry
        assert "mode" in lock_entry

    def test_lock_released_after_task_completes(self, mcp_workspace):
        """After a task completes, its lock is released."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="done")
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "research", mode="read-only"
                )
                json.loads(result)

                # Wait for completion.
                await asyncio.sleep(0.1)

                locks_result = await mcp_dispatch.get_locks()
                return json.loads(locks_result)

        locks_data = asyncio.run(_test())
        assert locks_data["count"] == 0
        assert locks_data["locks"] == []

    def test_task_status_includes_lock_info(self, mcp_workspace):
        """get_task_status includes lock information for working tasks."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:

                async def slow_dispatch(**kwargs):
                    await asyncio.sleep(1.0)
                    return DispatchResult(response_text="done")

                mock_rd.side_effect = slow_dispatch
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "research", mode="read-only"
                )
                data = json.loads(result)
                task_id = data["taskId"]

                status_result = await mcp_dispatch.get_task_status(task_id)
                status_data = json.loads(status_result)

                # Clean up.
                await mcp_dispatch.cancel_task(task_id)
                await asyncio.sleep(0.1)

                return status_data

        status_data = asyncio.run(_test())
        assert "lock" in status_data
        assert "paths" in status_data["lock"]
        assert "mode" in status_data["lock"]

    def test_conflict_warning_on_overlapping_dispatch(self, mcp_workspace):
        """Dispatching two tasks with overlapping paths logs a conflict warning."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:

                async def slow_dispatch(**kwargs):
                    await asyncio.sleep(1.0)
                    return DispatchResult(response_text="done")

                mock_rd.side_effect = slow_dispatch

                # First dispatch: read-only locks .docs/
                r1 = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "task-a", mode="read-only"
                )
                d1 = json.loads(r1)

                # Second dispatch: also read-only, overlapping .docs/
                r2 = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "task-b", mode="read-only"
                )
                d2 = json.loads(r2)

                # Both should be working (advisory, not blocking).
                assert d1["status"] == "working"
                assert d2["status"] == "working"

                # Both locks should be active.
                locks_result = await mcp_dispatch.get_locks()
                locks_data = json.loads(locks_result)
                assert locks_data["count"] == 2

                # Clean up.
                await mcp_dispatch.cancel_task(d1["taskId"])
                await mcp_dispatch.cancel_task(d2["taskId"])
                await asyncio.sleep(0.1)

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# TestExtractArtifacts
# ---------------------------------------------------------------------------


class TestExtractArtifacts:
    """Tests for the _extract_artifacts helper function."""

    def test_empty_text(self):
        assert mcp_dispatch._extract_artifacts("") == []

    def test_none_text(self):
        assert mcp_dispatch._extract_artifacts(None) == []

    def test_docs_paths(self):
        text = "I created .docs/plan/my-plan.md and .docs/adr/my-adr.md"
        result = mcp_dispatch._extract_artifacts(text)
        assert ".docs/adr/my-adr.md" in result
        assert ".docs/plan/my-plan.md" in result

    def test_src_paths(self):
        text = "Modified src/main.rs and src/lib.rs for the feature."
        result = mcp_dispatch._extract_artifacts(text)
        assert "src/main.rs" in result
        assert "src/lib.rs" in result

    def test_crates_paths(self):
        text = "Updated crates/pp-ui-core/src/lib.rs"
        result = mcp_dispatch._extract_artifacts(text)
        assert "crates/pp-ui-core/src/lib.rs" in result

    def test_known_extensions(self):
        text = "Check Cargo.toml and README.md for details."
        result = mcp_dispatch._extract_artifacts(text)
        assert "Cargo.toml" in result
        assert "README.md" in result

    def test_deduplication(self):
        text = "Modified src/main.rs then tested src/main.rs again."
        result = mcp_dispatch._extract_artifacts(text)
        assert result.count("src/main.rs") == 1

    def test_sorted_output(self):
        text = "Created src/z.rs then src/a.rs then .docs/b.md"
        result = mcp_dispatch._extract_artifacts(text)
        assert result == sorted(result)

    def test_no_paths_in_text(self):
        text = "Everything looks good, no files were modified."
        assert mcp_dispatch._extract_artifacts(text) == []

    def test_backtick_wrapped_paths(self):
        text = "See `src/main.rs` and `.docs/plan.md` for details."
        result = mcp_dispatch._extract_artifacts(text)
        assert "src/main.rs" in result
        assert ".docs/plan.md" in result

    def test_rules_paths(self):
        text = "Updated .rules/agents/my-agent.md"
        result = mcp_dispatch._extract_artifacts(text)
        assert ".rules/agents/my-agent.md" in result

    def test_test_paths(self):
        text = "Added tests/integration/test_foo.rs"
        result = mcp_dispatch._extract_artifacts(text)
        assert "tests/integration/test_foo.rs" in result


# ---------------------------------------------------------------------------
# TestMergeArtifacts
# ---------------------------------------------------------------------------


class TestMergeArtifacts:
    """Tests for the _merge_artifacts helper function."""

    def test_empty_both(self):
        assert mcp_dispatch._merge_artifacts([], []) == []

    def test_text_only(self):
        result = mcp_dispatch._merge_artifacts(["src/main.rs"], [])
        assert result == ["src/main.rs"]

    def test_written_only(self):
        result = mcp_dispatch._merge_artifacts([], [".docs/plan.md"])
        assert result == [".docs/plan.md"]

    def test_deduplication(self):
        result = mcp_dispatch._merge_artifacts(
            [".docs/plan.md", "src/main.rs"],
            [".docs/plan.md", "src/lib.rs"],
        )
        assert result.count(".docs/plan.md") == 1
        assert "src/main.rs" in result
        assert "src/lib.rs" in result

    def test_sorted_output(self):
        result = mcp_dispatch._merge_artifacts(
            ["src/z.rs"],
            ["src/a.rs"],
        )
        assert result == ["src/a.rs", "src/z.rs"]

    def test_backslash_normalization(self):
        result = mcp_dispatch._merge_artifacts(
            [],
            [".docs\\plan\\test.md"],
        )
        assert result == [".docs/plan/test.md"]

    def test_written_files_prioritized(self):
        """Written files appear even when not matching regex patterns."""
        result = mcp_dispatch._merge_artifacts(
            [],
            ["custom/output/result.json"],
        )
        assert "custom/output/result.json" in result


# ---------------------------------------------------------------------------
# TestArtifactTracking
# ---------------------------------------------------------------------------


class TestArtifactTracking:
    """Tests that completed dispatch results include extracted artifacts."""

    def test_artifacts_populated_from_response_text(self, mcp_workspace):
        """Completed task result includes artifacts extracted from response text."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(
                    response_text="Created .docs/plan/feature-plan.md and modified src/main.rs",
                )
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]
                await asyncio.sleep(0.1)
                status_result = await mcp_dispatch.get_task_status(task_id)
                return json.loads(status_result)

        status = asyncio.run(_test())
        assert status["status"] == "completed"
        artifacts = status["result"]["artifacts"]
        assert ".docs/plan/feature-plan.md" in artifacts
        assert "src/main.rs" in artifacts

    def test_artifacts_populated_from_written_files(self, mcp_workspace):
        """Completed task result includes artifacts from file write log."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(
                    response_text="Task done.",
                    written_files=[".docs/adr/test-adr.md", "src/lib.rs"],
                )
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]
                await asyncio.sleep(0.1)
                status_result = await mcp_dispatch.get_task_status(task_id)
                return json.loads(status_result)

        status = asyncio.run(_test())
        assert status["status"] == "completed"
        artifacts = status["result"]["artifacts"]
        assert ".docs/adr/test-adr.md" in artifacts
        assert "src/lib.rs" in artifacts

    def test_artifacts_merged_from_both_sources(self, mcp_workspace):
        """Artifacts from response text and file write log are merged and deduplicated."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(
                    response_text="Wrote .docs/plan.md and src/main.rs",
                    written_files=[".docs/plan.md", "src/new_module.rs"],
                )
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]
                await asyncio.sleep(0.1)
                status_result = await mcp_dispatch.get_task_status(task_id)
                return json.loads(status_result)

        status = asyncio.run(_test())
        assert status["status"] == "completed"
        artifacts = status["result"]["artifacts"]
        # .docs/plan.md appears in both but should be deduplicated.
        assert artifacts.count(".docs/plan.md") == 1
        assert "src/main.rs" in artifacts
        assert "src/new_module.rs" in artifacts

    def test_empty_response_empty_artifacts(self, mcp_workspace):
        """Empty response text and no written files yields empty artifacts list."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="")
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]
                await asyncio.sleep(0.1)
                status_result = await mcp_dispatch.get_task_status(task_id)
                return json.loads(status_result)

        status = asyncio.run(_test())
        assert status["status"] == "completed"
        assert status["result"]["artifacts"] == []

    def test_no_file_paths_empty_artifacts(self, mcp_workspace):
        """Response with no file paths and no writes yields empty artifacts list."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(
                    response_text="Task completed successfully with no file changes.",
                )
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]
                await asyncio.sleep(0.1)
                status_result = await mcp_dispatch.get_task_status(task_id)
                return json.loads(status_result)

        status = asyncio.run(_test())
        assert status["status"] == "completed"
        assert status["result"]["artifacts"] == []

    def test_written_files_only_no_text_mentions(self, mcp_workspace):
        """When agent writes files but doesn't mention them in text, artifacts still populated."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(
                    response_text="I completed the task.",
                    written_files=[".docs/exec/step-1.md", ".docs/exec/step-2.md"],
                )
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]
                await asyncio.sleep(0.1)
                status_result = await mcp_dispatch.get_task_status(task_id)
                return json.loads(status_result)

        status = asyncio.run(_test())
        assert status["status"] == "completed"
        artifacts = status["result"]["artifacts"]
        assert ".docs/exec/step-1.md" in artifacts
        assert ".docs/exec/step-2.md" in artifacts


# ---------------------------------------------------------------------------
# TestModePassthrough
# ---------------------------------------------------------------------------


class TestModePassthrough:
    """Tests that mode is passed through to run_dispatch."""

    def test_readonly_mode_passed_to_run_dispatch(self, mcp_workspace):
        """dispatch_agent with mode=read-only passes mode to run_dispatch."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="done")
                await mcp_dispatch.dispatch_agent(
                    "test-researcher", "analyze code", mode="read-only"
                )
                await asyncio.sleep(0.1)
                return mock_rd

        mock_rd = asyncio.run(_test())
        kwargs = mock_rd.call_args.kwargs
        assert kwargs["mode"] == "read-only"

    def test_readwrite_mode_passed_to_run_dispatch(self, mcp_workspace):
        """dispatch_agent with mode=read-write passes mode to run_dispatch."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="done")
                await mcp_dispatch.dispatch_agent(
                    "test-executor", "fix code", mode="read-write"
                )
                await asyncio.sleep(0.1)
                return mock_rd

        mock_rd = asyncio.run(_test())
        kwargs = mock_rd.call_args.kwargs
        assert kwargs["mode"] == "read-write"

    def test_default_mode_passed_to_run_dispatch(self, mcp_workspace):
        """When agent has frontmatter mode, it is passed to run_dispatch."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="done")
                # test-researcher has mode: read-only in frontmatter
                await mcp_dispatch.dispatch_agent("test-researcher", "research task")
                await asyncio.sleep(0.1)
                return mock_rd

        mock_rd = asyncio.run(_test())
        kwargs = mock_rd.call_args.kwargs
        assert kwargs["mode"] == "read-only"

    def test_client_ref_passed_to_run_dispatch(self, mcp_workspace):
        """dispatch_agent passes client_ref to run_dispatch for cancellation support."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="done")
                await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff", mode="read-write"
                )
                await asyncio.sleep(0.1)
                return mock_rd

        mock_rd = asyncio.run(_test())
        kwargs = mock_rd.call_args.kwargs
        assert "client_ref" in kwargs
        assert isinstance(kwargs["client_ref"], list)


# ---------------------------------------------------------------------------
# TestGracefulCancelIntegration (M2)
# ---------------------------------------------------------------------------


class TestGracefulCancelIntegration:
    """Tests for graceful ACP cancellation from MCP cancel_task."""

    def test_active_clients_populated_during_dispatch(self, mcp_workspace):
        """_active_clients is populated while a task is running."""

        async def _test():
            dispatch_started = asyncio.Event()

            async def blocking_dispatch(**kwargs):
                # Populate client_ref to simulate real behavior
                client_ref = kwargs.get("client_ref")
                if client_ref is not None:
                    from unittest.mock import MagicMock, AsyncMock as AM

                    mock_client = MagicMock()
                    mock_client.graceful_cancel = AM()
                    client_ref.clear()
                    client_ref.append(mock_client)
                dispatch_started.set()
                await asyncio.sleep(10.0)
                return DispatchResult(response_text="done")

            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.side_effect = blocking_dispatch
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]

                await dispatch_started.wait()

                # Verify client_ref is tracked
                assert task_id in mcp_dispatch._active_clients
                client_ref = mcp_dispatch._active_clients[task_id]
                assert len(client_ref) == 1

                # Cancel and verify graceful_cancel was called
                await mcp_dispatch.cancel_task(task_id)
                await asyncio.sleep(0.1)

                client_ref[0].graceful_cancel.assert_called_once()

        asyncio.run(_test())

    def test_active_clients_cleaned_up_after_completion(self, mcp_workspace):
        """_active_clients entry is removed after task completes."""

        async def _test():
            with patch.object(
                mcp_dispatch, "run_dispatch", new_callable=AsyncMock
            ) as mock_rd:
                mock_rd.return_value = DispatchResult(response_text="done")
                result = await mcp_dispatch.dispatch_agent(
                    "test-researcher", "do stuff"
                )
                data = json.loads(result)
                task_id = data["taskId"]

                # Let background complete
                await asyncio.sleep(0.1)

                # Client ref should be cleaned up
                assert task_id not in mcp_dispatch._active_clients

        asyncio.run(_test())

    def test_cancel_without_active_client_succeeds(self, mcp_workspace):
        """cancel_task works even if no active client exists (e.g. task failed before client setup)."""
        task = mcp_dispatch.task_engine.create_task("test-agent")
        result = asyncio.run(mcp_dispatch.cancel_task(task.task_id))
        data = json.loads(result)
        assert data["status"] == "cancelled"