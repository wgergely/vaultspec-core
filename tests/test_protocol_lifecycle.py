from __future__ import annotations

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import pytest  # noqa: E402

from acp_dispatch import AgentNotFoundError, DispatchResult, run_dispatch  # noqa: E402


class TestACPLifecycle:
    """Real agent dispatch lifecycle tests via ACP transport."""

    @pytest.mark.asyncio
    async def test_successful_dispatch(self):
        """Dispatching french-croissant returns a non-empty response."""
        result = await run_dispatch(
            agent_name="french-croissant",
            initial_task="Say bonjour in one sentence.",
            model_override="gemini-2.5-flash",
            interactive=False,
            debug=False,
            quiet=True,
            mode="read-only",
        )
        assert isinstance(result, DispatchResult)
        assert len(result.response_text) > 0

    @pytest.mark.asyncio
    async def test_french_response(self):
        """french-croissant responds in French."""
        result = await run_dispatch(
            agent_name="french-croissant",
            initial_task="Say hello and mention your love of croissants.",
            model_override="gemini-2.5-flash",
            interactive=False,
            debug=False,
            quiet=True,
            mode="read-only",
        )
        text_lower = result.response_text.lower()
        assert any(
            word in text_lower
            for word in ["bonjour", "croissant", "français", "boulanger", "pâtisserie"]
        )

    @pytest.mark.asyncio
    async def test_dispatch_result_structure(self):
        """DispatchResult contains expected fields after successful dispatch."""
        result = await run_dispatch(
            agent_name="french-croissant",
            initial_task="One word: bonjour.",
            model_override="gemini-2.5-flash",
            interactive=False,
            debug=False,
            quiet=True,
            mode="read-only",
        )
        assert hasattr(result, "response_text")
        assert hasattr(result, "written_files")
        assert hasattr(result, "session_id")
        assert isinstance(result.written_files, list)

    @pytest.mark.asyncio
    async def test_nonexistent_agent_raises(self):
        """Dispatching a nonexistent agent raises AgentNotFoundError."""
        with pytest.raises(AgentNotFoundError):
            await run_dispatch(
                agent_name="agent-that-does-not-exist",
                initial_task="This should fail.",
                interactive=False,
                debug=False,
                quiet=True,
            )

    @pytest.mark.asyncio
    async def test_session_id_populated(self):
        """Completed dispatch populates session_id on the result."""
        result = await run_dispatch(
            agent_name="french-croissant",
            initial_task="Bonjour!",
            model_override="gemini-2.5-flash",
            interactive=False,
            debug=False,
            quiet=True,
            mode="read-only",
        )
        # session_id should be set after a successful ACP session
        assert result.session_id is not None
        assert len(result.session_id) > 0


class TestSessionResume:
    """Tests for session resume support structures."""

    def test_dispatch_result_includes_session_id(self):
        """DispatchResult has a session_id field that defaults to None."""
        result = DispatchResult(response_text="hello")
        assert result.session_id is None

        result_with_sid = DispatchResult(response_text="hello", session_id="ses-123")
        assert result_with_sid.session_id == "ses-123"

    def test_session_resume_feature_gate(self):
        """_SESSION_RESUME_ENABLED reads from PP_DISPATCH_SESSION_RESUME env var.

        Uses subprocess to avoid importlib.reload() which breaks class identity
        for DispatchResult across test modules.
        """
        import os
        import subprocess

        check_script = (
            "import sys; sys.path.insert(0, r'{}'); "
            "import acp_dispatch; print(acp_dispatch._SESSION_RESUME_ENABLED)"
        ).format(_SCRIPTS_DIR)

        # Enabled
        env_on = {**os.environ, "PP_DISPATCH_SESSION_RESUME": "1"}
        proc = subprocess.run(
            [sys.executable, "-c", check_script],
            env=env_on,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "True"

        # Disabled (default)
        env_off = {
            k: v for k, v in os.environ.items() if k != "PP_DISPATCH_SESSION_RESUME"
        }
        proc = subprocess.run(
            [sys.executable, "-c", check_script],
            env=env_off,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "False"
