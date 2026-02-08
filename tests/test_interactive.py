from __future__ import annotations

import io
import sys
import typing
from unittest.mock import AsyncMock, MagicMock

import pytest

from acp.client.connection import ClientSideConnection
from acp.schema import PromptResponse
from orchestration.dispatch import (
    _interactive_loop,
)


@pytest.mark.asyncio
class TestInteractiveLoop:
    async def test_one_shot_mode(self):
        """Verify that loop exits after one prompt if interactive=False."""
        conn = AsyncMock(spec=ClientSideConnection)
        conn.prompt.return_value = PromptResponse(stop_reason="end_turn")
        proc = MagicMock()
        proc.returncode = None

        await _interactive_loop(
            conn=typing.cast("ClientSideConnection", conn),
            session_id="s1",
            agent_name="test",
            initial_prompt="hello",
            debug=False,
            interactive=False,
            proc=proc,
            logger_instance=None,
        )

        conn.prompt.assert_called_once()

    async def test_interactive_mode_exit(self, monkeypatch):
        """Verify loop exit via user command using real stdin pipe."""
        conn = AsyncMock(spec=ClientSideConnection)
        conn.prompt.return_value = PromptResponse(stop_reason="end_turn")
        proc = MagicMock()
        proc.returncode = None

        # Simulate real input via a stream
        fake_stdin = io.StringIO("exit\n")
        monkeypatch.setattr(sys, "stdin", fake_stdin)

        # Ensure isatty is true for the loop to continue to input
        # Wait, if we use a stream, isatty is false.
        # Let's check _interactive_loop logic.
        # if not sys.stdin.isatty(): break

        # We need to mock isatty to True but use real readline
        monkeypatch.setattr(fake_stdin, "isatty", lambda: True)

        await _interactive_loop(
            conn=typing.cast("ClientSideConnection", conn),
            session_id="s2",
            agent_name="test",
            initial_prompt="hello",
            debug=False,
            interactive=True,
            proc=proc,
            logger_instance=None,
        )

        # Should prompt once initially
        conn.prompt.assert_called_once()
