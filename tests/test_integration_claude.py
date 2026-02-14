"""Integration test for Claude provider dispatch.

Requires:
- Claude CLI installed and on PATH
- Claude CLI authenticated (handles its own auth)
- Network access to Anthropic API

Skipped automatically if prerequisites are missing.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from orchestration.dispatch import run_dispatch
from protocol.acp.types import DispatchResult
from protocol.providers.claude import ClaudeProvider

if TYPE_CHECKING:
    import pathlib

_has_claude_cli = shutil.which("claude") is not None

pytestmark = [
    pytest.mark.integration,
    pytest.mark.claude,
    pytest.mark.skipif(not _has_claude_cli, reason="Claude CLI not installed"),
]


@pytest.fixture
def mock_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """Creates a minimal workspace structure."""
    (tmp_path / ".vault").mkdir()
    (tmp_path / ".vaultspec" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    return tmp_path


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_claude_dispatch_lifecycle(mock_root):
    """Verify run_dispatch with real Claude CLI returns a valid result."""
    (mock_root / ".vaultspec" / "agents" / "tester.md").write_text(
        "---\ntier: MEDIUM\n---\n\n# Persona\n"
        "You are Jean-Claude, a helpful assistant.\n"
        "Your name is Jean-Claude. Always introduce yourself by name.\n"
        "Keep your responses extremely short.\n",
        encoding="utf-8",
    )

    provider = ClaudeProvider()

    result = await run_dispatch(
        agent_name="tester",
        root_dir=mock_root,
        initial_task="What is your name? Reply with only your name.",
        provider_instance=provider,
        interactive=False,
        debug=True,
    )

    assert isinstance(result, DispatchResult)
    assert result.session_id is not None
    assert len(result.response_text) > 0
    assert "Jean-Claude" in result.response_text
