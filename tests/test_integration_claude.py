from __future__ import annotations

import pathlib
import pytest
from orchestration.dispatch import run_dispatch
from protocol.acp.types import DispatchResult

@pytest.fixture
def mock_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """Creates a minimal workspace structure."""
    (tmp_path / ".docs").mkdir()
    (tmp_path / ".rules" / "agents").mkdir(parents=True)
    return tmp_path

@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.asyncio
async def test_claude_integration(mock_root):
    """Real integration test for Claude provider."""
    (mock_root / ".rules" / "agents" / "tester.md").write_text(
        """---
tier: MEDIUM
---
# Persona
You are a helpful assistant.
""", encoding="utf-8"
    )

    result = await run_dispatch(
        agent_name="tester",
        root_dir=mock_root,
        initial_task="Say hello",
        model_override="claude-3-5-sonnet-20241022",
        interactive=False
    )

    assert isinstance(result, DispatchResult)
    assert len(result.response_text) > 0