from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from acp.schema import PromptResponse
from orchestration.dispatch import (
    _interactive_loop,
)

# ---------------------------------------------------------------------------
# TestOneShotMode
# ---------------------------------------------------------------------------


class TestOneShotMode:
    @pytest.mark.asyncio
    async def test_oneshot_calls_prompt_once(self):
        """In one-shot (non-interactive) mode, loop exits after one turn."""
        conn = AsyncMock()
        # Mock response with any stop reason
        conn.prompt.return_value = PromptResponse(stop_reason="end_turn")

        proc = MagicMock()
        proc.returncode = None

        await _interactive_loop(
            conn=conn,  # type: ignore
            session_id="s1",
            agent_name="test",
            initial_prompt="hello",
            debug=False,
            interactive=False,  # One-shot
            proc=proc,
            logger_instance=None,
        )

        assert conn.prompt.call_count == 1
        # Should not wait for input
        assert proc.wait.call_count == 0


# ---------------------------------------------------------------------------
# TestInteractiveMode
# ---------------------------------------------------------------------------


class TestInteractiveMode:
    @pytest.mark.asyncio
    async def test_non_tty_exits_after_first_turn(self):
        """When stdin is not a TTY, interactive mode exits after first response."""
        conn = AsyncMock()
        conn.prompt.return_value = PromptResponse(stop_reason="end_turn")

        proc = MagicMock()
        proc.returncode = None

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False

            await _interactive_loop(
                conn=conn,  # type: ignore
                session_id="s2",
                agent_name="test",
                initial_prompt="hello",
                debug=False,
                interactive=True,
                proc=proc,
                logger_instance=None,
            )

        assert conn.prompt.call_count == 1
