"""Integration tests for the interactive ACP loop.

These tests require a real ACP connection and subprocess, which are only
available in an integration environment.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


class TestInteractiveLoop:
    """Tests for _interactive_loop that require real ACP connection."""

    @pytest.mark.asyncio
    async def test_one_shot_mode(self):
        """Verify that loop exits after one prompt if interactive=False.

        Integration: requires real ACP ClientSideConnection and subprocess.
        """
        pytest.skip("requires real ACP connection and subprocess")

    @pytest.mark.asyncio
    async def test_interactive_mode_exit(self):
        """Verify loop exit via user command using real stdin pipe.

        Integration: requires real ACP ClientSideConnection and subprocess.
        """
        pytest.skip("requires real ACP connection and subprocess")
