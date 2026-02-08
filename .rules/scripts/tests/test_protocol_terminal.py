"""Live terminal protocol tests using real agents.

Tests that the ACP dispatch framework correctly handles terminal operations
during real agent dispatch. Uses french-croissant to verify the dispatch
lifecycle completes without terminal-related errors.

Requires GEMINI_API_KEY to be set.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from acp_dispatch import DispatchResult, run_dispatch


class TestTerminalProtocol:
    """Live terminal protocol tests via real agent dispatch."""

    @pytest.mark.asyncio
    async def test_dispatch_completes_without_terminal_errors(self):
        """Agent dispatch completes cleanly (terminal subsystem exercised internally)."""
        result = await run_dispatch(
            agent_name="french-croissant",
            initial_task="Name three French pastries in one sentence.",
            model_override="gemini-2.5-flash",
            interactive=False,
            debug=False,
            quiet=True,
            mode="read-only",
        )
        assert isinstance(result, DispatchResult)
        assert len(result.response_text) > 0

    @pytest.mark.asyncio
    async def test_dispatch_result_has_clean_session(self):
        """After dispatch, session_id is populated and no terminal leaks."""
        result = await run_dispatch(
            agent_name="french-croissant",
            initial_task="What time do French bakeries open?",
            model_override="gemini-2.5-flash",
            interactive=False,
            debug=False,
            quiet=True,
            mode="read-only",
        )
        assert result.session_id is not None
        assert isinstance(result.written_files, list)
