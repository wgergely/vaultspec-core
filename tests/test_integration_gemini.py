"""Integration test for Gemini provider dispatch.

Requires:
- Gemini CLI installed and on PATH
- GEMINI_API_KEY set in environment
- Network access to Google AI API

Skipped automatically if prerequisites are missing.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from orchestration.dispatch import run_dispatch
from protocol.acp.types import DispatchResult
from protocol.providers.gemini import GeminiProvider

if TYPE_CHECKING:
    import pathlib

_has_gemini_cli = shutil.which("gemini") is not None

pytestmark = [
    pytest.mark.integration,
    pytest.mark.gemini,
    pytest.mark.skipif(not _has_gemini_cli, reason="Gemini CLI not installed"),
]


@pytest.fixture
def mock_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """Creates a minimal workspace structure."""
    (tmp_path / ".vault").mkdir()
    (tmp_path / ".vaultspec" / "agents").mkdir(parents=True)
    (tmp_path / ".gemini").mkdir()
    (tmp_path / ".gemini" / "settings.json").write_text("{}", encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_gemini_dispatch_lifecycle(mock_root):
    """Verify run_dispatch with real Gemini CLI returns a valid result."""
    (mock_root / ".vaultspec" / "agents" / "tester.md").write_text(
        "---\ntier: LOW\n---\n\n# Persona\n"
        "You are a helpful assistant. Keep your responses extremely short.\n",
        encoding="utf-8",
    )

    provider = GeminiProvider()

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
    assert len(result.response_text) > 0
