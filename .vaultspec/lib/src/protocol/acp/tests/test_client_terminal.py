"""Terminal sandbox tests for SubagentClient.

Covers: create_terminal read-only guard in SubagentClient.
"""

from __future__ import annotations

import pytest

from protocol.acp.client import SubagentClient

from .conftest import TEST_PROJECT

pytestmark = [pytest.mark.unit]


class TestCreateTerminalReadOnly:
    """Verify that create_terminal is blocked in read-only mode."""

    @pytest.mark.asyncio
    async def test_create_terminal_denied_readonly(self):
        """SubagentClient(mode='read-only').create_terminal() raises ValueError."""
        client = SubagentClient(root_dir=TEST_PROJECT, mode="read-only")
        with pytest.raises(ValueError):
            await client.create_terminal(
                command="bash",
                session_id="test-session",
            )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_terminal_allowed_readwrite(self):
        """Terminal creation succeeds in read-write mode.

        Integration: requires real subprocess creation.
        """
        pytest.skip("requires real subprocess for terminal creation")

    @pytest.mark.asyncio
    async def test_create_terminal_denied_message_mentions_readonly(self):
        """Error message from denied terminal creation mentions 'read-only'."""
        client = SubagentClient(root_dir=TEST_PROJECT, mode="read-only")
        with pytest.raises(ValueError, match="read-only"):
            await client.create_terminal(
                command="ls",
                session_id="test-session",
            )

    @pytest.mark.asyncio
    async def test_default_mode_is_readwrite(self):
        """SubagentClient defaults to read-write mode."""
        client = SubagentClient(root_dir=TEST_PROJECT)
        assert client.mode == "read-write"
