"""Integration tests for Gemini provider with real API.

Requires GEMINI_API_KEY environment variable.
Run with: pytest -m integration -m gemini
"""

from __future__ import annotations

import os

import pytest

from acp_dispatch import run_dispatch

pytestmark = [
    pytest.mark.integration,
    pytest.mark.gemini,
]

SKIP_REASON = "GEMINI_API_KEY not set"


def has_gemini_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


@pytest.mark.skipif(not has_gemini_key(), reason=SKIP_REASON)
class TestGeminiIntegration:
    @pytest.mark.asyncio
    async def test_french_croissant_oneshot(self):
        """Run french-croissant agent with gemini provider in one-shot mode."""
        await run_dispatch(
            agent_name="french-croissant",
            initial_task="Say hello in French",
            provider_override="gemini",
            interactive=False,
            debug=False,
        )

    @pytest.mark.asyncio
    async def test_french_croissant_with_model_override(self):
        """Run french-croissant with explicit gemini-2.5-flash model."""
        await run_dispatch(
            agent_name="french-croissant",
            initial_task="What is your favorite pastry? Answer in French.",
            model_override="gemini-2.5-flash",
            interactive=False,
            debug=False,
        )

    @pytest.mark.asyncio
    async def test_gemini_3_flash_if_available(self):
        """Run with gemini-3-flash-preview model."""
        await run_dispatch(
            agent_name="french-croissant",
            initial_task="Bonjour! Dites-moi quelque chose.",
            model_override="gemini-3-flash-preview",
            interactive=False,
            debug=False,
        )
