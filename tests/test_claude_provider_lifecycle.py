from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from orchestration.dispatch import run_dispatch
from protocol.acp.types import DispatchResult
from protocol.providers.claude import ClaudeProvider

if TYPE_CHECKING:
    import pathlib


@pytest.fixture
def mock_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """Creates a minimal workspace structure."""
    (tmp_path / ".docs").mkdir()
    (tmp_path / ".rules" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    return tmp_path


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.asyncio
async def test_claude_provider_lifecycle(mock_root):
    """Verifies that run_dispatch works with the real ClaudeProvider and real CLI."""
    # 1. Setup the agent
    (mock_root / ".rules" / "agents" / "tester.md").write_text(
        """---
tier: MEDIUM
---
# Persona
You are a helpful assistant. Keep your responses extremely short.
""",
        encoding="utf-8",
    )

    provider = ClaudeProvider()

    # 2. Run dispatch
    # We use a very simple task
    result = await run_dispatch(
        agent_name="tester",
        root_dir=mock_root,
        initial_task="Please say only the word 'ACK'.",
        provider_instance=provider,
        interactive=False,
        debug=True,
    )

    assert isinstance(result, DispatchResult)
    assert result.session_id is not None
    assert "ACK" in result.response_text.upper()
