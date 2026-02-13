from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from orchestration.dispatch import run_dispatch
from protocol.acp.types import DispatchResult

if TYPE_CHECKING:
    import pathlib


@pytest.fixture
def mock_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """Creates a minimal workspace structure."""
    (tmp_path / ".vault").mkdir()
    (tmp_path / ".vaultspec" / "agents").mkdir(parents=True)
    (tmp_path / ".gemini").mkdir()
    (tmp_path / ".gemini" / "settings.json").write_text("{}", encoding="utf-8")
    return tmp_path


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.asyncio
async def test_gemini_integration(mock_root):
    """Real integration test for Gemini provider."""
    (mock_root / ".vaultspec" / "agents" / "tester.md").write_text(
        """---
tier: LOW
---
# Persona
You are a helpful assistant.
""",
        encoding="utf-8",
    )

    result = await run_dispatch(
        agent_name="tester",
        root_dir=mock_root,
        initial_task="Say hello",
        model_override="gemini-2.0-flash-exp",
        interactive=False,
    )

    assert isinstance(result, DispatchResult)
    assert len(result.response_text) > 0
