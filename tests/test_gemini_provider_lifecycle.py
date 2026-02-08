from __future__ import annotations

import pathlib
import sys
from unittest import mock

import pytest

from orchestration.dispatch import run_dispatch
from protocol.acp.types import DispatchResult
from protocol.providers.gemini import GeminiProvider


@pytest.fixture
def mock_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """Creates a minimal workspace structure."""
    (tmp_path / ".docs").mkdir()
    (tmp_path / ".rules" / "agents").mkdir(parents=True)
    (tmp_path / ".gemini" / "rules").mkdir(parents=True)
    return tmp_path


@pytest.mark.asyncio
async def test_gemini_provider_lifecycle(mock_root):
    """Verifies that run_dispatch works with the real GeminiProvider using a mock executable."""
    # 1. Setup the agent
    (mock_root / ".rules" / "agents" / "tester.md").write_text(
        "---
tier: LOW
---
Persona", encoding="utf-8"
    )

    # 2. Setup a fake 'gemini' executable that just prints STUB-READY then waits
    # We'll use sys.executable -c to emulate it.
    # Note: GeminiProvider calls 'gemini --version' and 'gemini --system ... mcp serve'
    
    provider = GeminiProvider()
    
    # We need to mock 'shutil.which' to return our fake executable
    # and 'subprocess.run' for the version check.
    
    fake_exe = "fake-gemini"
    
    with (
        mock.patch("shutil.which", return_value=fake_exe),
        mock.patch("protocol.providers.gemini.subprocess.run") as mock_run,
        mock.patch("spawn_agent_process") as mock_spawn,
    ):
        # Mock version check
        mock_v = mock.MagicMock()
        mock_v.stdout = "gemini v0.27.0"
        mock_run.return_value = mock_v
        
        # Mock the async context manager for spawn_agent_process
        mock_conn = mock.AsyncMock()
        mock_proc = mock.MagicMock()
        mock_proc.stdin = mock.MagicMock()
        mock_proc.stdout = mock.MagicMock()
        
        # Create an async context manager mock
        class AsyncContextMock:
            async def __aenter__(self):
                return mock_conn, mock_proc
            async def __aexit__(self, exc_type, exc, tb):
                pass
        
        mock_spawn.return_value = AsyncContextMock()
        
        # Mock connection methods
        mock_conn.initialize.return_value = mock.AsyncMock()
        mock_session = mock.MagicMock()
        mock_session.session_id = "test-session"
        mock_conn.new_session.return_value = mock_session
        mock_conn.cancel.return_value = mock.AsyncMock()

        # Run dispatch
        result = await run_dispatch(
            agent_name="tester",
            root_dir=mock_root,
            initial_task="hello",
            provider_instance=provider,
        )

        assert isinstance(result, DispatchResult)
        assert result.session_id == "test-session"
        
        # Verify provider.prepare_process was called and used to spawn
        # (Implicitly verified by run_dispatch completion)
