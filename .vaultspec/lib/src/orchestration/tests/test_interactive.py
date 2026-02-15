from __future__ import annotations

import io
import sys
import typing

import pytest

pytestmark = [pytest.mark.unit]

from acp.schema import PromptResponse  # noqa: E402

from orchestration.subagent import (  # noqa: E402
    _interactive_loop,
)

if typing.TYPE_CHECKING:
    from acp.client.connection import ClientSideConnection


# ---------------------------------------------------------------------------
# Fakes replacing MagicMock / AsyncMock
# ---------------------------------------------------------------------------


class _FakeConn:
    """Stand-in for ClientSideConnection with an async prompt()."""

    def __init__(self):
        self.prompt_calls = 0

    async def prompt(self, *_args, **_kwargs):
        self.prompt_calls += 1
        return PromptResponse(stop_reason="end_turn")

    def assert_called_once(self):
        assert self.prompt_calls == 1


class _FakeProc:
    """Stand-in for a subprocess (only returncode is read)."""

    returncode = None


@pytest.mark.asyncio
class TestInteractiveLoop:
    async def test_one_shot_mode(self):
        """Verify that loop exits after one prompt if interactive=False."""
        conn = _FakeConn()
        proc = _FakeProc()

        await _interactive_loop(
            conn=typing.cast("ClientSideConnection", conn),
            session_id="s1",
            agent_name="test",
            initial_prompt="hello",
            debug=False,
            interactive=False,
            proc=proc,  # type: ignore[arg-type]
            logger_instance=None,
        )

        conn.assert_called_once()

    async def test_interactive_mode_exit(self, monkeypatch):
        """Verify loop exit via user command using real stdin pipe."""
        conn = _FakeConn()
        proc = _FakeProc()

        # Simulate real input via a stream
        fake_stdin = io.StringIO("exit\n")
        monkeypatch.setattr(sys, "stdin", fake_stdin)

        # input() reads from sys.stdin usually, but let's be explicit
        monkeypatch.setattr("builtins.input", lambda _: fake_stdin.readline().rstrip())

        # We need to mock isatty to True for the loop to continue to input
        monkeypatch.setattr(fake_stdin, "isatty", lambda: True)

        await _interactive_loop(
            conn=typing.cast("ClientSideConnection", conn),
            session_id="s2",
            agent_name="test",
            initial_prompt="hello",
            debug=False,
            interactive=True,
            proc=proc,  # type: ignore[arg-type]
            logger_instance=None,
        )

        # Should prompt once initially
        conn.assert_called_once()
