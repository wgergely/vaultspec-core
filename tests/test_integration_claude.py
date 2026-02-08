"""Integration tests for Claude provider with real API.

Requires ANTHROPIC_API_KEY environment variable.
Run with: pytest -m integration -m claude
"""

from __future__ import annotations

import os

import pytest

from acp_dispatch import run_dispatch

pytestmark = [
    pytest.mark.integration,
    pytest.mark.claude,
]

SKIP_REASON = "ANTHROPIC_API_KEY not set"


def has_anthropic_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.mark.skipif(not has_anthropic_key(), reason=SKIP_REASON)
class TestClaudeIntegration:
    @pytest.mark.asyncio
    async def test_french_croissant_oneshot(self):
        """Run french-croissant agent with claude provider in one-shot mode."""
        await run_dispatch(
            agent_name="french-croissant",
            initial_task="Say hello in French",
            provider_override="claude",
            interactive=False,
            debug=False,
        )

    @pytest.mark.asyncio
    async def test_french_croissant_with_model_override(self):
        """Run french-croissant with explicit claude-haiku-4-5 model."""
        await run_dispatch(
            agent_name="french-croissant",
            initial_task="What is your favorite pastry? Answer in French.",
            model_override="claude-haiku-4-5",
            interactive=False,
            debug=False,
        )

    @pytest.mark.asyncio
    async def test_claude_sonnet(self):
        """Run with claude-sonnet-4-5 model."""
        await run_dispatch(
            agent_name="french-croissant",
            initial_task="Bonjour! Parlez-moi des croissants.",
            model_override="claude-sonnet-4-5",
            interactive=False,
            debug=False,
        )
