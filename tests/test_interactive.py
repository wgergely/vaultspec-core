"""Tests for interactive loop, one-shot mode, and provider fallback logic."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from acp.schema import PromptResponse, TextContentBlock
from acp_dispatch import _interactive_loop, run_dispatch, GeminiDispatchClient, SessionLogger, AgentNotFoundError


# ---------------------------------------------------------------------------
# TestOneShotMode
# ---------------------------------------------------------------------------

class TestOneShotMode:
    @pytest.mark.asyncio
    async def test_oneshot_calls_prompt_once(self):
        """In one-shot mode (interactive=False), prompt is called exactly once."""
        mock_conn = AsyncMock()
        mock_conn.prompt.return_value = PromptResponse(stop_reason="end_turn")

        mock_proc = MagicMock()
        mock_proc.returncode = None

        logger = MagicMock(spec=SessionLogger)
        logger.log = MagicMock()

        await _interactive_loop(
            conn=mock_conn,
            session_id="test-session",
            agent_name="test-agent",
            initial_prompt="Do something",
            debug=False,
            interactive=False,
            proc=mock_proc,
            logger=logger,
        )

        mock_conn.prompt.assert_called_once()

    @pytest.mark.asyncio
    async def test_oneshot_exits_regardless_of_stop_reason(self):
        """One-shot mode exits after one turn even if stop_reason is not end_turn."""
        mock_conn = AsyncMock()
        mock_conn.prompt.return_value = PromptResponse(stop_reason="max_tokens")

        mock_proc = MagicMock()
        mock_proc.returncode = None

        logger = MagicMock(spec=SessionLogger)
        logger.log = MagicMock()

        await _interactive_loop(
            conn=mock_conn,
            session_id="test-session",
            agent_name="test-agent",
            initial_prompt="Something",
            debug=False,
            interactive=False,
            proc=mock_proc,
            logger=logger,
        )

        # Should still only be called once
        assert mock_conn.prompt.call_count == 1


# ---------------------------------------------------------------------------
# TestInteractiveMode
# ---------------------------------------------------------------------------

class TestInteractiveMode:
    @pytest.mark.asyncio
    async def test_non_tty_exits_after_first_turn(self):
        """When stdin is not a TTY, interactive mode exits after first response."""
        mock_conn = AsyncMock()
        mock_conn.prompt.return_value = PromptResponse(stop_reason="end_turn")

        mock_proc = MagicMock()
        mock_proc.returncode = None

        logger = MagicMock(spec=SessionLogger)
        logger.log = MagicMock()

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            await _interactive_loop(
                conn=mock_conn,
                session_id="test-session",
                agent_name="test-agent",
                initial_prompt="Interactive test",
                debug=False,
                interactive=True,
                proc=mock_proc,
                logger=logger,
            )

        assert mock_conn.prompt.call_count == 1

    @pytest.mark.asyncio
    async def test_process_exit_during_wait(self):
        """If the process exits while waiting for input, the loop should break."""
        mock_conn = AsyncMock()
        mock_conn.prompt.return_value = PromptResponse(stop_reason="end_turn")

        mock_proc = MagicMock()
        # After first prompt, process has exited
        mock_proc.returncode = 0

        logger = MagicMock(spec=SessionLogger)
        logger.log = MagicMock()

        await _interactive_loop(
            conn=mock_conn,
            session_id="test-session",
            agent_name="test-agent",
            initial_prompt="Test",
            debug=False,
            interactive=True,
            proc=mock_proc,
            logger=logger,
        )

        assert mock_conn.prompt.call_count == 1


# ---------------------------------------------------------------------------
# TestProviderFallback
# ---------------------------------------------------------------------------

class TestProviderFallback:
    @pytest.mark.asyncio
    async def test_provider_override_no_fallback(self):
        """When provider_override is set and agent not found, AgentNotFoundError is raised."""
        with pytest.raises(AgentNotFoundError):
            await run_dispatch(
                agent_name="nonexistent-agent",
                initial_task="Test",
                provider_override="gemini",
                interactive=False,
                debug=False,
            )
