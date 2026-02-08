from __future__ import annotations

import typing
from unittest.mock import AsyncMock, MagicMock, patch

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

        # Check that prompt was called. Note: actual blocks are complex,
        # just verify it was called.
        conn.prompt.assert_called_once()

    async def test_interactive_mode_exit(self):
        """Verify loop exit via user command."""
        conn = AsyncMock(spec=ClientSideConnection)
        conn.prompt.return_value = PromptResponse(stop_reason="end_turn")
        proc = MagicMock()
        proc.returncode = None

        with (
            patch("builtins.input", side_cache=["exit"]),
            patch("sys.stdin") as mock_stdin,
        ):
            mock_stdin.isatty.return_value = False

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
