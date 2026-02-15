from __future__ import annotations

import pathlib
import sys
import tempfile

import pytest
from acp.schema import (
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
    PermissionOption,
    PlanEntry,
    SessionInfoUpdate,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
)

from protocol.acp.client import SubagentClient

from .conftest import TEST_PROJECT

pytestmark = [pytest.mark.unit]

# ---------------------------------------------------------------------------
# TestRequestPermission
# ---------------------------------------------------------------------------


class TestRequestPermission:
    @pytest.fixture
    def client(self):
        # SubagentClient is the unified ACP client
        return SubagentClient(root_dir=pathlib.Path("."), debug=False)

    @pytest.mark.asyncio
    async def test_allow_once_selected(self, client):
        options = [
            PermissionOption(option_id="allow", name="Allow", kind="allow_once"),
            PermissionOption(option_id="reject", name="Reject", kind="reject_once"),
        ]
        tool_call = ToolCallUpdate(tool_call_id="tc-1")
        result = await client.request_permission(
            options=options, session_id="s1", tool_call=tool_call
        )
        assert result.outcome.outcome == "selected"
        assert result.outcome.optionId == "allow"

    @pytest.mark.asyncio
    async def test_allow_always_selected(self, client):
        options = [
            PermissionOption(option_id="reject", name="Reject", kind="reject_once"),
            PermissionOption(
                option_id="allow-session", name="Allow Session", kind="allow_always"
            ),
        ]
        tool_call = ToolCallUpdate(tool_call_id="tc-2")
        result = await client.request_permission(
            options=options, session_id="s1", tool_call=tool_call
        )
        assert result.outcome.outcome == "selected"
        assert result.outcome.optionId == "allow-session"

    @pytest.mark.asyncio
    async def test_only_reject_options(self, client):
        options = [
            PermissionOption(option_id="reject-1", name="Reject", kind="reject_once"),
            PermissionOption(
                option_id="reject-2", name="Reject Always", kind="reject_always"
            ),
        ]
        tool_call = ToolCallUpdate(tool_call_id="tc-3")
        result = await client.request_permission(
            options=options, session_id="s1", tool_call=tool_call
        )
        # Falls through to first option when no allow found
        assert result.outcome.outcome == "selected"
        assert result.outcome.optionId == "reject-1"

    @pytest.mark.asyncio
    async def test_empty_options(self, client):
        tool_call = ToolCallUpdate(tool_call_id="tc-4")
        result = await client.request_permission(
            options=[], session_id="s1", tool_call=tool_call
        )
        assert result.outcome.outcome == "selected"
        assert result.outcome.optionId == "allow"  # Default fallback

    @pytest.mark.asyncio
    async def test_none_options(self, client):
        tool_call = ToolCallUpdate(tool_call_id="tc-5")
        result = await client.request_permission(
            options=None, session_id="s1", tool_call=tool_call
        )
        assert result.outcome.outcome == "selected"

    @pytest.mark.asyncio
    async def test_validates_against_schema(self, client):
        """Verify the response can be validated by the ACP schema."""
        from acp.schema import RequestPermissionResponse

        options = [
            PermissionOption(option_id="approve", name="Approve", kind="allow_once"),
        ]
        tool_call = ToolCallUpdate(tool_call_id="tc-6")
        result = await client.request_permission(
            options=options, session_id="s1", tool_call=tool_call
        )
        assert isinstance(result, RequestPermissionResponse)
        assert result.outcome.outcome == "selected"


# ---------------------------------------------------------------------------
# TestSessionUpdate
# ---------------------------------------------------------------------------


class TestSessionUpdate:
    @pytest.fixture
    def client(self):
        return SubagentClient(root_dir=TEST_PROJECT, debug=False)

    @pytest.mark.asyncio
    async def test_agent_message_chunk(self, client, capsys):
        update = AgentMessageChunk(
            session_update="agent_message_chunk",
            content=TextContentBlock(type="text", text="Hello from agent"),
        )
        await client.session_update("s1", update)
        captured = capsys.readouterr()
        assert "Hello from agent" in captured.out
        assert client.response_text == "Hello from agent"

    @pytest.mark.asyncio
    async def test_agent_thought_chunk(self, client, capsys):
        update = AgentThoughtChunk(
            session_update="agent_thought_chunk",
            content=TextContentBlock(type="text", text="Thinking..."),
        )
        await client.session_update("s1", update)
        captured = capsys.readouterr()
        assert "Thinking..." in captured.err

    @pytest.mark.asyncio
    async def test_tool_call_start(self, client, capsys):
        update = ToolCallStart(
            session_update="tool_call",
            tool_call_id="tc-1",
            title="read_file",
        )
        await client.session_update("s1", update)
        captured = capsys.readouterr()
        # SubagentClient prints [Tool] to stderr
        assert "read_file" in captured.err

    @pytest.mark.asyncio
    async def test_tool_call_progress(self, client):
        update = ToolCallProgress(
            session_update="tool_call_update",
            tool_call_id="tc-1",
            title="read_file",
            status="in_progress",
        )
        await client.session_update("s1", update)
        # Progress currently does nothing
        pass

    @pytest.mark.asyncio
    async def test_agent_plan_update(self, client):
        update = AgentPlanUpdate(
            session_update="plan",
            entries=[
                PlanEntry(content="Step 1", status="completed", priority="high"),
                PlanEntry(content="Step 2", status="pending", priority="medium"),
            ],
        )
        await client.session_update("s1", update)
        # Plan update currently does nothing
        pass

    @pytest.mark.asyncio
    async def test_debug_mode_shows_info_updates(self):
        client = SubagentClient(root_dir=TEST_PROJECT, debug=True)
        update = SessionInfoUpdate(session_update="session_info_update")
        await client.session_update("s1", update)
        # Info update currently does nothing
        pass


# ---------------------------------------------------------------------------
# TestFileIO
# ---------------------------------------------------------------------------


class TestFileIO:
    @pytest.fixture
    def client(self):
        return SubagentClient(root_dir=TEST_PROJECT, debug=False)

    @pytest.mark.asyncio
    async def test_read_text_file(self, client, test_root_dir):
        # We need client.root_dir to be the same as where the file is
        client.root_dir = test_root_dir
        result = await client.read_text_file(
            path=str(test_root_dir / "test.txt"),
            session_id="s1",
        )
        assert "Hello from test workspace" in result.content

    @pytest.mark.asyncio
    async def test_read_text_file_with_line_and_limit(self, client, test_root_dir):
        client.root_dir = test_root_dir
        result = await client.read_text_file(
            path=str(test_root_dir / "test.txt"),
            session_id="s1",
            line=2,
            limit=1,
        )
        assert "Line 2" in result.content
        assert "Line 3" not in result.content

    @pytest.mark.asyncio
    async def test_read_text_file_outside_workspace(self, client, test_root_dir):
        client.root_dir = test_root_dir
        with tempfile.TemporaryDirectory() as td:
            outside = pathlib.Path(td) / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            with pytest.raises(ValueError, match="outside workspace"):
                await client.read_text_file(path=str(outside), session_id="s1")

    @pytest.mark.asyncio
    async def test_read_text_file_nonexistent(self, client, test_root_dir):
        client.root_dir = test_root_dir
        with pytest.raises(FileNotFoundError):
            await client.read_text_file(
                path=str(test_root_dir / "nonexistent.txt"),
                session_id="s1",
            )

    @pytest.mark.asyncio
    async def test_write_text_file(self, client, test_root_dir):
        client.root_dir = test_root_dir
        target = test_root_dir / "output.txt"
        await client.write_text_file(
            content="Written by test",
            path=str(target),
            session_id="s1",
        )
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "Written by test"

    @pytest.mark.asyncio
    async def test_write_text_file_nested(self, client, test_root_dir):
        client.root_dir = test_root_dir
        target = test_root_dir / "deep" / "nested" / "file.txt"
        await client.write_text_file(
            content="Nested content",
            path=str(target),
            session_id="s1",
        )
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "Nested content"

    @pytest.mark.asyncio
    async def test_write_text_file_outside_workspace(self, client, test_root_dir):
        client.root_dir = test_root_dir
        with tempfile.TemporaryDirectory() as td:
            outside = pathlib.Path(td) / "output.txt"
            with pytest.raises(ValueError, match="outside workspace"):
                await client.write_text_file(
                    content="Sneaky",
                    path=str(outside),
                    session_id="s1",
                )


# ---------------------------------------------------------------------------
# TestTerminalLifecycle
# ---------------------------------------------------------------------------


class TestTerminalLifecycle:
    @pytest.fixture
    def client(self):
        return SubagentClient(root_dir=TEST_PROJECT, debug=False)

    @pytest.mark.asyncio
    async def test_create_terminal(self, client, test_root_dir):
        client.root_dir = test_root_dir
        result = await client.create_terminal(
            command=sys.executable,
            session_id="s1",
            args=["-c", "print('hello')"],
        )
        assert result.terminal_id is not None
        terminal_id = result.terminal_id
        assert terminal_id in client._terminals

        # Cleanup
        await client.release_terminal(session_id="s1", terminal_id=terminal_id)

    @pytest.mark.asyncio
    async def test_terminal_output(self, client, test_root_dir):
        client.root_dir = test_root_dir
        result = await client.create_terminal(
            command=sys.executable,
            session_id="s1",
            args=["-c", "print('terminal_test_output')"],
        )
        terminal_id = result.terminal_id

        # Wait for exit
        await client.wait_for_terminal_exit(session_id="s1", terminal_id=terminal_id)

        # Read output
        output = await client.terminal_output(session_id="s1", terminal_id=terminal_id)
        assert "terminal_test_output" in output.output

        await client.release_terminal(session_id="s1", terminal_id=terminal_id)

    @pytest.mark.asyncio
    async def test_wait_for_exit_returns_code(self, client, test_root_dir):
        client.root_dir = test_root_dir
        result = await client.create_terminal(
            command=sys.executable,
            session_id="s1",
            args=["-c", "exit(0)"],
        )
        terminal_id = result.terminal_id
        exit_result = await client.wait_for_terminal_exit(
            session_id="s1", terminal_id=terminal_id
        )
        assert exit_result.exit_code == 0
        await client.release_terminal(session_id="s1", terminal_id=terminal_id)

    @pytest.mark.asyncio
    async def test_kill_terminal(self, client, test_root_dir):
        client.root_dir = test_root_dir
        result = await client.create_terminal(
            command=sys.executable,
            session_id="s1",
            args=["-c", "import time; time.sleep(60)"],
        )
        terminal_id = result.terminal_id

        await client.kill_terminal(session_id="s1", terminal_id=terminal_id)
        exit_result = await client.wait_for_terminal_exit(
            session_id="s1", terminal_id=terminal_id
        )
        assert exit_result.exit_code is not None

        await client.release_terminal(session_id="s1", terminal_id=terminal_id)

    @pytest.mark.asyncio
    async def test_release_terminal_removes_tracking(self, client, test_root_dir):
        client.root_dir = test_root_dir
        result = await client.create_terminal(
            command=sys.executable,
            session_id="s1",
            args=["-c", "print('done')"],
        )
        terminal_id = result.terminal_id
        await client.wait_for_terminal_exit(session_id="s1", terminal_id=terminal_id)
        await client.release_terminal(session_id="s1", terminal_id=terminal_id)
        assert terminal_id not in client._terminals

    @pytest.mark.asyncio
    async def test_terminal_output_unknown_id(self, client):
        output = await client.terminal_output(session_id="s1", terminal_id="unknown-id")
        assert output.output == ""
        assert output.truncated is False

    @pytest.mark.asyncio
    async def test_wait_unknown_terminal(self, client):
        exit_result = await client.wait_for_terminal_exit(
            session_id="s1", terminal_id="unknown-id"
        )
        assert exit_result.exit_code is None
