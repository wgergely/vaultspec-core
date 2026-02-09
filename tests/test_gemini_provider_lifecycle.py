from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from orchestration.dispatch import run_dispatch
from protocol.acp.types import DispatchResult
from protocol.providers.gemini import GeminiProvider

if TYPE_CHECKING:
    import pathlib


@pytest.fixture
def mock_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """Creates a minimal workspace structure."""
    (tmp_path / ".docs").mkdir()
    (tmp_path / ".rules" / "agents").mkdir(parents=True)
    (tmp_path / ".gemini" / "rules").mkdir(parents=True)
    # Create a minimal settings file to avoid gemini CLI error
    (tmp_path / ".gemini" / "settings.json").write_text("{}", encoding="utf-8")
    return tmp_path


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.asyncio
async def test_gemini_provider_lifecycle(mock_root):
    """Verifies that run_dispatch works with the real GeminiProvider and real CLI."""
    # 1. Setup the agent
    (mock_root / ".rules" / "agents" / "tester.md").write_text(
        """---
tier: LOW
---
# Persona
You are a helpful assistant. Keep your responses extremely short.
""",
        encoding="utf-8",
    )

    provider = GeminiProvider()

    # 2. Run dispatch
    # We use a very simple task to minimize costs/latency
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
